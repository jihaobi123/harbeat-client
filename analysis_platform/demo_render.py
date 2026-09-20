"""Render frozen DEMO plans. Sample execution logs are not browser telemetry."""
from pathlib import Path
import hashlib,json,subprocess,math
import numpy as np
import soundfile as sf
from scipy.signal import firwin,fftconvolve


def run(args):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=600)
    if p.returncode:raise RuntimeError(p.stderr[-2500:])
    return p


def fade_curve(t,start,end,incoming):
    if end<=start:raise ValueError('invalid fade range')
    value=np.clip((t-start)/(end-start),0,1)
    return value if incoming else 1-value


def mid_eq(audio,sr,cut_db,low,high):
    if not 0<low<high<sr/2:raise ValueError('invalid EQ band')
    kernel=firwin(1025,[low,high],pass_zero=False,fs=sr)
    band=np.column_stack([fftconvolve(audio[:,c],kernel,mode='same') for c in range(audio.shape[1])])
    return (audio+(np.power(10,np.asarray(cut_db)/20)-1)[:,None]*band).astype(np.float32)


def low_eq(audio,sr,cut_db,cutoff):
    cut_db=np.asarray(cut_db)
    if not 0<cutoff<sr/2 or not np.isfinite(cut_db).all() or np.any(cut_db>0):
        raise ValueError('low EQ requires finite attenuation-only values')
    kernel=firwin(2049,cutoff,fs=sr)
    band=np.column_stack([fftconvolve(audio[:,c],kernel,mode='same') for c in range(audio.shape[1])])
    return (audio+(np.power(10,cut_db/20)-1)[:,None]*band).astype(np.float32)


def validate_pair(p,preview):
    if p.get('status') not in ('ready','needs_review'):raise ValueError('blocked or invalid plan cannot render')
    if p['status']=='needs_review' and not preview:raise ValueError('preview permission required')


def compile_set(tracks,pairs,sr,preview):
    if len(pairs)!=len(tracks)-1 or len(tracks)<2:raise ValueError('set requires N-1 transitions')
    result=[]
    for p in pairs:validate_pair(p,preview)
    for i,track in enumerate(tracks):
        incoming=pairs[i-1] if i else None;outgoing=pairs[i] if i<len(pairs) else None
        if incoming and incoming['b_report_id']!=track['report_id']:raise ValueError('incoming identity mismatch')
        if outgoing and outgoing['a_report_id']!=track['report_id']:raise ValueError('outgoing identity mismatch')
        rate=incoming['mapping']['b']['rate'] if incoming else outgoing['mapping']['a']['rate']
        if outgoing and abs(rate-outgoing['mapping']['a']['rate'])>1e-7:raise ValueError('inconsistent adjacent rate')
        if not .5<=rate<=2:raise ValueError('render rate outside supported range')
        cue=incoming['mapping']['b']['source_cue_sec'] if incoming else 0
        if cue!=0:raise ValueError('this renderer preserves file start; tail cue not supported')
        offset=(result[i-1]['offset_sec']+incoming['mapping']['b']['playback_start_sec']) if incoming else 0
        if offset<0:raise ValueError('negative preroll')
        trim=min([p['gains'][which+'_trim_db'] for p,which in [(incoming,'b'),(outgoing,'a')] if p])
        result.append({**track,'rate':rate,'offset_sec':offset,'offset_sample':round(offset*sr),'trim_db':trim,
                       'frames':round(track['end_sec']/rate*sr)})
    return result


def measure(path):
    p=run(['ffmpeg','-hide_banner','-nostats','-i',path,'-af','loudnorm=I=-18:TP=-1:LRA=11:print_format=json','-f','null','-'])
    return json.loads(p.stderr[p.stderr.rfind('{'):p.stderr.rfind('}')+1])


def render(document,out,preview=False):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);sr=44100
    pairs=document['pairs'];tracks=compile_set(document['tracks'],pairs,sr,preview)
    total=max(t['offset_sample']+t['frames'] for t in tracks)
    if total>sr*3600:raise ValueError('audition exceeds one hour')
    mix=np.zeros((total,2),dtype=np.float32);execution=[];segments=out/'segments';segments.mkdir(exist_ok=True)
    for i,track in enumerate(tracks):
        source=Path(track['path'])
        if hashlib.sha256(source.read_bytes()).hexdigest()!=track['audio_sha256']:raise ValueError('audio SHA mismatch')
        dest=segments/f'{i+1:02d}.wav'
        run(['ffmpeg','-y','-v','error','-i',source,'-af',f"atrim=end={track['end_sec']:.9f},asetpts=PTS-STARTPTS,atempo={track['rate']:.12f}",'-ar',str(sr),'-ac','2','-c:a','pcm_f32le',dest])
        x,actual_sr=sf.read(dest,dtype='float32',always_2d=True)
        expected=track['frames'];delta=len(x)-expected
        if abs(delta)>sr*.12:raise ValueError('decoder/time stretch length differs by more than 120ms')
        x=np.pad(x,((0,max(0,expected-len(x))),(0,0)))[:expected]
        t=np.arange(len(x))/sr;gain=np.ones(len(x));cut=np.zeros(len(x));applied={};low_cut=np.zeros(len(x));low_cutoff=None
        if i:
            p=pairs[i-1];start=p['mapping']['b']['playback_start_sec']
            incoming_gain=fade_curve(t,p['entry_sec']-start,p['handoff_sec']-start,True)
            gain*=incoming_gain
            applied['entry_sample_local']=int(np.flatnonzero(incoming_gain>0)[0])
            applied['full_sample_local']=int(np.flatnonzero(incoming_gain>=1)[0])
            eq=p['eq'];restore0=eq['restore_start_sec']-start;restore1=eq['restore_end_sec']-start
            cut=eq['b_mid_cut_db']*(1-np.clip((t-restore0)/(restore1-restore0),0,1))
            if eq['b_mid_cut_db']!=0:
                applied['eq_restore_sample_local']=int(np.flatnonzero(cut>eq['b_mid_cut_db'])[0])
                applied['eq_normal_sample_local']=int(np.flatnonzero(cut>=0)[0])
                x=mid_eq(x,sr,cut,eq['low_hz'],eq['high_hz'])
            if p.get('low_eq'):
                low=p['low_eq'];low_cutoff=low['cutoff_hz']
                rs=low['b_restore_start_sec']-start;re=low['b_restore_end_sec']-start
                low_cut=low['b_cut_db']*(1-np.clip((t-rs)/(re-rs),0,1))
                applied['low_restore_sample_local']=int(np.flatnonzero(low_cut>low['b_cut_db'])[0])
                applied['low_normal_sample_local']=int(np.flatnonzero(low_cut>=0)[0])
        if i<len(pairs):
            outgoing_gain=fade_curve(t,pairs[i]['entry_sec'],pairs[i]['handoff_sec'],False)
            gain*=outgoing_gain
            active=np.flatnonzero(outgoing_gain>0)
            applied['silent_sample_local']=int(active[-1]+1) if len(active) else 0
            if pairs[i].get('low_eq'):
                low=pairs[i]['low_eq']
                if low_cutoff is not None and low_cutoff!=low['cutoff_hz']:raise ValueError('inconsistent low EQ cutoff')
                low_cutoff=low['cutoff_hz']
                outgoing_cut=low['a_end_cut_db']*np.clip((t-low['entry_sec'])/(low['handoff_sec']-low['entry_sec']),0,1)
                low_cut=np.minimum(low_cut,outgoing_cut)
                applied['low_exit_start_sample_local']=int(np.flatnonzero(outgoing_cut<0)[0])
        if low_cutoff is not None:
            x=low_eq(x,sr,low_cut,low_cutoff)
        # Five-millisecond start and 20ms terminal fade only suppress file-edge clicks.
        if i==0:gain*=np.clip(t/.005,0,1)
        if i==len(tracks)-1:gain*=np.clip((len(x)/sr-t)/.02,0,1)
        x*=gain[:,None]*10**(track['trim_db']/20)
        if not np.isfinite(x).all():raise ValueError('nonfinite render output')
        sf.write(dest,x,sr,subtype='FLOAT');pos=track['offset_sample'];mix[pos:pos+len(x)]+=x
        execution.append({'track':track['title'],'offset_sample':pos,'rate':track['rate'],'trim_db':track['trim_db'],
                          'planned_frames':expected,'decoder_length_delta_samples':delta,'rendered_frames':len(x),'applied_automation':applied})
        print('rendered',track['title'],flush=True)
    raw=out/'mix-float.wav';sf.write(raw,mix,sr,subtype='FLOAT')
    before=measure(raw);peak=float(before['input_tp']);attenuation=min(0,-1.2-peak)
    mix*=10**(attenuation/20)
    wav=out/'HarBeat-DEMO-1.0-preview.wav';sf.write(wav,mix,sr,subtype='PCM_24')
    after=measure(wav)
    if float(after['input_tp'])> -1.0:raise ValueError('final true peak exceeded target')
    run(['ffmpeg','-y','-v','error','-i',wav,'-c:a','libmp3lame','-b:a','256k',out/'HarBeat-DEMO-1.0-preview.mp3'])
    mp3_levels=measure(out/'HarBeat-DEMO-1.0-preview.mp3')
    if float(mp3_levels['input_tp'])> -1:
        extra=-1.3-float(mp3_levels['input_tp']);mix*=10**(extra/20);attenuation+=extra
        sf.write(wav,mix,sr,subtype='PCM_24')
        run(['ffmpeg','-y','-v','error','-i',wav,'-c:a','libmp3lame','-b:a','256k',out/'HarBeat-DEMO-1.0-preview.mp3'])
        after=measure(wav);mp3_levels=measure(out/'HarBeat-DEMO-1.0-preview.mp3')
        if float(mp3_levels['input_tp'])> -1:raise ValueError('MP3 true peak exceeded target')
    clips=[];events=[]
    for i,p in enumerate(pairs):
        origin=tracks[i]['offset_sec'];entry=origin+p['entry_sec'];handoff=origin+p['handoff_sec']
        lo=max(0,round((entry-8)*sr));hi=min(total,round((handoff+8)*sr))
        clip=out/f'transition-{i+1:02d}.wav';sf.write(clip,mix[lo:hi],sr,subtype='PCM_24')
        run(['ffmpeg','-y','-v','error','-i',clip,'-c:a','libmp3lame','-b:a','256k',clip.with_suffix('.mp3')])
        clips.append({'number':i+1,'a':p['a_title'],'b':p['b_title'],'file':clip.with_suffix('.mp3').name,
                      'entry_sec':entry,'handoff_sec':handoff,'clip_start_sec':lo/sr,'overlap_bars':p['overlap_bars'],'mid_cut_db':p['eq']['b_mid_cut_db']})
        for event in p['events']:
            planned=origin+event['planned_sec']
            # B-local automation and segment placement each quantize independently.
            bpos=execution[i+1]['offset_sample'];applied=execution[i+1]['applied_automation']
            if event['name']=='B 音频启动':sample=bpos
            elif event['name']=='B 中频开始恢复':sample=bpos+applied['eq_restore_sample_local']
            elif event['name']=='开始可听交接':sample=bpos+applied['entry_sample_local']
            else:sample=max(execution[i]['offset_sample']+execution[i]['applied_automation']['silent_sample_local'],bpos+applied['full_sample_local'])
            events.append({'pair':i+1,'name':event['name'],'planned_sec':planned,'actual_sec':sample/sr,
                           'actual_sample':sample,'delta_ms':(sample/sr-planned)*1000,'clock':'offline_render_sample_clock'})
        if p.get('low_eq'):
            low=p['low_eq'];applied=execution[i+1]['applied_automation'];pos=execution[i+1]['offset_sample']
            low_events=[('B 低频开始恢复',origin+low['b_restore_start_sec'],pos+applied['low_restore_sample_local']),
                        ('B 低频恢复正常',origin+low['b_restore_end_sec'],pos+applied['low_normal_sample_local']),
                        ('A 低频开始衰减',origin+low['entry_sec'],execution[i]['offset_sample']+execution[i]['applied_automation']['low_exit_start_sample_local'])]
            for name,planned,sample in low_events:
                events.append({'pair':i+1,'name':name,'planned_sec':planned,'actual_sec':sample/sr,'actual_sample':sample,
                               'delta_ms':(sample/sr-planned)*1000,'clock':'offline_render_sample_clock'})
    log={'schema':'harbeat.offline_render_execution','status':'rendered_preview' if preview else 'rendered','sample_rate':sr,
         'duration_sec':len(mix)/sr,'tracks':execution,'events':events,'clips':clips,'global_attenuation_db':attenuation,
         'levels_before':before,'levels_after':after,'mp3_levels':mp3_levels,'wav_sha256':hashlib.sha256(wav.read_bytes()).hexdigest(),
         'limitations':['Actual means applied DSP schedule, not browser playback or independently detected music boundaries.',
                       'Regular-grid and structural candidates have not been confirmed by a human listener.',
                       'FFmpeg atempo preserves pitch; transient placement and artifacts still require listening.']}
    (out/'execution.json').write_text(json.dumps(log,ensure_ascii=False,indent=2))
    (out/'plan.json').write_text(json.dumps(document,ensure_ascii=False,indent=2))
    return log
