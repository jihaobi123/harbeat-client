#!/usr/bin/env python3
"""Re-render the colleague's delivered six-song decisions without V2 audio policy."""
import json,sys,subprocess,shutil,math
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from analysis_platform.demo_v3 import compile_plan,load_renderer,sha256,PLAN_SHA256
from analysis_platform.demo_render import measure

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'mixing/vendor/colleague_demo_v1'
OUT=ROOT/'outputs/demo-render-v3/listen'
WORK=OUT.parent/'work'


def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2))


def compare(reference,rendered):
    paths=[]
    for name,source in [('reference',reference),('rendered',rendered)]:
        target=WORK/(name+'-decoded.f32')
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(source),'-f','f32le','-acodec','pcm_f32le','-ar','44100','-ac','2',str(target)],check=True)
        paths.append(np.memmap(target,dtype='float32',mode='r'))
    x,y=paths;n=min(len(x),len(y));xx=yy=xy=ee=0.;peak=0.
    for start in range(0,n,44100*20):
        a=x[start:min(n,start+44100*20)].astype('float64');b=y[start:min(n,start+44100*20)].astype('float64');d=a-b
        xx+=float(np.sum(a*a));yy+=float(np.sum(b*b));xy+=float(np.sum(a*b));ee+=float(np.sum(d*d));peak=max(peak,float(np.max(abs(d))))
    return {'method':'same decoded sample index, stereo 44100Hz float32; no gain correction, alignment or time warp',
            'reference_decoded_frames':len(x)//2,'v3_decoded_frames':len(y)//2,'compared_frames':n//2,
            'same_frame_count':len(x)==len(y),'decoded_samples_identical':len(x)==len(y) and ee==0,
            'waveform_cosine_similarity':xy/math.sqrt(xx*yy),'difference_rms_dbfs':10*math.log10(ee/n) if ee else None,
            'reference_relative_error_db':10*math.log10(ee/xx) if ee else None,'max_absolute_sample_difference':peak,
            'mp3_bytes_identical':sha256(reference)==sha256(rendered),'interpretation':'Numerical signal comparison, not an independent listening-quality score.'}


def main():
    global OUT, WORK
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True,help='JSON array (or {tracks: [...]}) with title, audio_sha256, path for six originals')
    parser.add_argument('--reference',type=Path,help='Optional original colleague MP3 for exact comparison')
    parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args();OUT=args.output.resolve();WORK=OUT.parent/(OUT.name+'-work')
    source_data=json.loads(args.sources.read_text())
    sources=source_data['tracks'] if isinstance(source_data,dict) else source_data
    for row in sources:
        path=Path(row['path'])
        row['path']=str(path if path.is_absolute() else (args.sources.resolve().parent/path))
    if args.reference and sha256(args.reference)!='d87180977de7494bf3e2e4e2640049bd50c712fb4d25c8fffe6861eb93182a41':
        raise ValueError('reference checksum mismatch')
    OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
    if sha256(SRC/'mix_plan.json')!=PLAN_SHA256:raise ValueError('delivered plan checksum mismatch')
    peer=json.loads((SRC/'mix_plan.json').read_text())
    plan=compile_plan(peer,sources);plan['id']=__import__('hashlib').sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
    if (OUT/'plan.json').exists() and json.loads((OUT/'plan.json').read_text())['id']!=plan['id']:raise ValueError('output plan differs; refusing overwrite')
    save(OUT/'plan.json',plan)
    commands=[];api=load_renderer(SRC/'algorithm_demo_transition_logic_1_0.py',commands);ffmpeg=api['_ffmpeg']()
    segments=[];segment_log=[]
    for i,t in enumerate(plan['tracks']):
        dest=WORK/f'segment-{i+1:02d}.wav';segments.append(dest)
        print('Rendering',i+1,t['title'],flush=True)
        api['render_segment'](ffmpeg=ffmpeg,source_path=Path(t['source_path']),output_path=dest,**t['render'])
        info=sf.info(dest)
        segment_log.append({'title':t['title'],'frames':info.frames,'duration_sec':info.duration,'sample_rate':info.samplerate,'sha256':sha256(dest),'applied_parameters':t['render']})
    overlaps=[t['overlap_seconds'] for t in plan['transitions']]
    wav=OUT/'HarBeat-DEMO-3.0-reproduction.wav';mp3=OUT/'HarBeat-DEMO-3.0-reproduction.mp3'
    times,duration=api['render_crossfaded_mix'](ffmpeg,segments,overlaps,wav)
    snippets=api['render_snippets'](ffmpeg,wav,times,WORK/'snippets')
    for source,dest in [(wav,mp3)]+[(path,OUT/f'transition-{i+1:02d}.mp3') for i,path in enumerate(snippets)]:
        api['_run']([ffmpeg,'-y','-v','error','-i',str(source),'-c:a','libmp3lame','-b:a','320k',str(dest)])
    reference=None
    comparison={'status':'not_provided','interpretation':'No reference audio supplied; this run makes no identity claim.'}
    if args.reference:
        reference=OUT/'colleague-original.mp3';shutil.copy2(args.reference,reference)
        comparison=compare(reference,mp3)
    save(OUT/'comparison.json',comparison)
    transition_log=[];offset=0
    for i,t in enumerate(plan['transitions']):
        # The original acrossfade uses milliseconds rounded by its own format string.
        overlap_samples=round(float(f"{overlaps[i]:.3f}")*44100)
        offset+=segment_log[i]['frames']-overlap_samples
        transition_log.append({'position':i+1,'from':t['from'],'to':t['to'],'delivered_transition_sec':t['transition_time_seconds'],
                               'replay_original_function_transition_sec':times[i],
                               'difference_from_delivered_ms':(times[i]-t['transition_time_seconds'])*1000,
                               'acrossfade_start_sample_before_limiter':offset,'acrossfade_end_sample_before_limiter':offset+overlap_samples,
                               'ffmpeg_overlap_literal':f"{overlaps[i]:.3f}",'both_vocal_detected':t['both_vocal_detected'],
                               'note':'Frame schedule before original limiter; limiter latency and browser output timing are not measured here.'})
    execution={'schema':'harbeat.colleague_replay_execution.v3','plan_id':plan['id'],'duration_sec':duration,'tracks':segment_log,'transitions':transition_log,
               'ffmpeg_version':subprocess.check_output([ffmpeg,'-version'],text=True).splitlines()[0],
               'wav_levels':measure(wav),'mp3_levels':measure(mp3),'reference_levels':measure(reference) if reference else None,
               'commands':commands,'comparison':comparison,'wav_sha256':sha256(wav),'mp3_sha256':sha256(mp3),
               'policy_changes_from_colleague':[],'route_recomputed':False,'human_confirmed':False}
    save(OUT/'execution.json',execution)
    shutil.copy2(SRC/'mix_plan.json',OUT/'colleague-plan.json');shutil.copy2(SRC/'algorithm_demo_transition_logic_1_0.py',OUT/'colleague-renderer.py')
    print(json.dumps({'duration':duration,'comparison':comparison,'levels':execution['mp3_levels']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
