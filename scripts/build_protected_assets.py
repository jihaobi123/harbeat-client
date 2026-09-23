#!/usr/bin/env python3
"""Create candidate intro grids and voice-free-lane assets; never certify reviews."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import re


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()


def merged(sections):
    result=[]
    for s in sorted(sections,key=lambda x:x['start']):
        if result and result[-1]['label']==s['label'] and abs(result[-1]['end']-s['start'])<.001: result[-1]['end']=s['end']
        else: result.append(dict(s))
    return result


def grid(beats,bars,duration):
    anchor=min(range(len(beats)),key=lambda i:abs(beats[i]-bars[0]))
    if abs(beats[anchor]-bars[0])>.04: raise ValueError('Downbeat cannot be bound to existing beats')
    leading=[beats[i] for i in range(anchor%4,anchor,4)]
    return leading+[x for x in bars if x<duration]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('input',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--nas-root',type=Path,required=True);args=ap.parse_args()
    source=json.loads(args.input.read_text());tracks=source['tracks'];evidence={};media=args.output/'media';media.mkdir(parents=True,exist_ok=True)
    work=Path('/tmp/harbeat-protected-assets');work.mkdir(exist_ok=True)
    version=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]
    for t in tracks:
        tid=t['id'];old_bars=t['bars'];t['bars']=grid(t.pop('sourceBeats'),old_bars,t['duration']);t['sections']=merged(t['sections']);sources=t.pop('stemSources');paths=[]
        for stem in sources.values():
            p=(args.nas_root/stem['storage_key']).resolve();assert p.is_relative_to(args.nas_root.resolve());assert sha(p)==stem['sha256'];paths.append(p)
        backing=work/(tid+'-float.wav')
        # Rebuild from verified sources; never trust an unversioned cache.
        cmd=['ffmpeg','-y','-nostdin','-v','error']
        for p in paths:cmd+=['-i',str(p)]
        cmd+=['-filter_complex','[0:a][1:a][2:a]amix=inputs=3:normalize=0:duration=shortest[out]','-map','[out]','-t',str(t['duration']),'-ar','44100','-ac','2','-c:a','pcm_f32le',str(backing)]
        subprocess.run(cmd,check=True)
        stats=subprocess.run(['ffmpeg','-nostdin','-i',str(backing),'-af','astats=metadata=0:reset=0','-f','null','-'],capture_output=True,text=True,check=True).stderr
        peaks=[float(v) for v in re.findall(r'Peak level dB: ([-+0-9.]+)',stats)]
        assert peaks, 'No measured backing peak'
        peak=max(peaks);gain_db=min(0.,-.5-peak)
        t['native']['url']='/analysis-lab-static/v3-live-baseline-20260922/'+t['native']['url']
        exits=[]
        for i,s in enumerate(t['sections']):
            cut=next((v for v in t['bars'] if v>=s['end']-.001),None)
            if cut is not None and 0<=cut-s['end']<=.5 and cut<t['duration']-.1:exits.append({'id':f'episode-{i}','cut':cut,'sectionEnd':s['end'],'start':s['start'],'label':s['label']})
        ev={'exits':exits,'windows':{},'grid':{'status':'candidate_requires_listening','method':'observed beats, 4-beat phase from first existing downbeat; no uniform time extrapolation','originalFirstBar':old_bars[0],'leadingCandidateBars':[x for x in t['bars'] if x<old_bars[0]]}}
        windows=[]
        for si,s in enumerate(t['sections'][:4]):
            indices=[i for i,v in enumerate(t['bars']) if s['start']<=v<s['end']]
            if not indices:continue
            i=indices[0]
            for n in [2,4]:
                if i+n>=len(t['bars']):continue
                start,end=t['bars'][i],t['bars'][i+n]
                if end>s['end']+.001 or end+12>t['duration']:continue
                wid=f'guard-{si}-{n}';w={'id':wid,'start':start,'end':end,'bars':n,'role':s['label'],'energy':0,'variants':{}}
                ev['windows'][wid]={'start':start,'end':end,'sectionStart':s['start'],'sectionEnd':s['end'],'lane':'instrumental','sourceHashes':[v['sha256'] for v in sources.values()],'gridSource':'intro_phase_candidate' if start<old_bars[0] else 'existing_grid_candidate','status':'needs_listening_no_obvious_vocal_leakage_and_clean_body_start','backingPeakDbFS':peak,'backingGainDb':gain_db}
                for a in tracks:
                    if a['id']==tid:continue
                    duration=n*240/a['bpm'];rate=(end-start)/duration
                    if not .8<=rate<=1.2:continue
                    filename=f'{tid}-{wid}-{a["id"][6:]}.flac';dest=media/filename
                    filt=f'volume={gain_db:.9f}dB,atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS,atempo={rate:.9f},apad=whole_dur={duration:.9f},atrim=end={duration:.9f}'
                    cmd=['ffmpeg','-y','-nostdin','-v','error','-i',str(backing),'-af',filt,'-ar','44100','-ac','2','-c:a','flac','-sample_fmt','s16','-frame_size','4096',str(dest)]
                    subprocess.run(cmd,check=True)
                    actual=float(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(dest)]))['format']['duration'])
                    assert abs(actual-duration)<1/44100
                    w['variants'][a['id']]={'url':'media/'+filename,'sha256':sha(dest),'duration':actual,'bytes':dest.stat().st_size,'rate':rate,'recipe':filt,'sourceBackingSha256':sha(backing)}
                if w['variants']:windows.append(w)
        t['windows']=windows;t.pop('mixProfile',None);evidence[tid]=ev
        print(t['title'],'intro bars',len(ev['grid']['leadingCandidateBars']),'windows',len(windows),'exits',len(exits),flush=True)
    doc={'schema':'harbeat.protected.assets.v1','tracks':tracks,'evidence':evidence,'producer':{'ffmpeg':version,'instrumental':'drums + bass + other, linear sum with no vocal stem; residual leakage requires human check'},'reviews':{},'limits':['All grids, structural and vocal boundaries are candidates. No human review generated.','Candidate intro downbeats use existing beat observations with inferred phase.','Only first 150 seconds retained; no fallback to arbitrary bar exits.']}
    (args.output/'guard-catalog.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2))
    print('DONE',sum(len(w['variants']) for t in tracks for w in t['windows']),flush=True)

if __name__=='__main__':main()
