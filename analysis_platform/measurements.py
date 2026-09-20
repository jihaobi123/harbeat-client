"""Explicit acoustic measurements; all derived values remain outside the mix engine."""
from pathlib import Path
import hashlib
import numpy as np
from scipy.signal import find_peaks
from .report import intervals


def finite(value):
    return float(value) if np.isfinite(value) else None


def db(rms):
    return float(20*np.log10(rms)) if rms > 1e-12 else None


def loudness(y, sr):
    import pyloudnorm as pyln
    if len(y)/sr < .4 or not np.any(y):
        return None
    return finite(pyln.Meter(sr).integrated_loudness(y))


def dynamics(y, sr, sections):
    y=np.asarray(y,dtype=float)
    power=y*y if y.ndim==1 else np.mean(y*y,axis=1)
    duration=len(y)/sr
    # Non-overlapping 50 ms energy windows. Stereo channels are not summed.
    hop=max(1,round(sr*.05))
    starts=np.arange(0,len(y),hop)
    rms=np.sqrt(np.add.reduceat(power,starts)/np.minimum(hop,len(y)-starts))
    peak=float(rms.max()) if len(rms) else 0
    active=rms>=peak*.05 if peak>1e-12 else np.zeros(len(rms),dtype=bool)
    gated=rms[active]
    dr=db(np.percentile(gated,95)/np.percentile(gated,5)) if len(gated) else None
    # Whole file, including its leading/trailing silence; sample-weighted last frame.
    weights=np.minimum(hop,len(y)-starts)
    silence=float(np.sum(weights[~active])/len(y))
    points=[{'start':float(s/sr),'end':float(min(s+hop,len(y))/sr),'rms_dbfs':db(v)} for s,v in zip(starts,rms)]
    output=[]
    for seg in intervals(sections):
        start,end=max(0.,seg['start']),min(duration,seg['end'])
        if end<=start:continue
        a,b=int(start*sr),int(end*sr)
        part=y[a:b]
        level=db(np.sqrt(np.mean(power[a:b])))
        lu=loudness(part,sr)
        previous=output[-1] if output else {}
        adjacent=bool(previous) and abs(previous['end']-start)<=1/sr
        output.append({'start':start,'end':end,'label':seg['label'],'rms_dbfs':level,'integrated_lufs':lu,
            'delta_rms_db':level-previous['rms_dbfs'] if adjacent and level is not None and previous['rms_dbfs'] is not None else None,
            'delta_lufs':lu-previous['integrated_lufs'] if adjacent and lu is not None and previous['integrated_lufs'] is not None else None,
            'loudness_reason':None if lu is not None else 'silent_or_shorter_than_400ms'})
    return {'method':'rms_percentiles_and_bs1770_v1','duration':duration,'sample_rate':sr,
        'channels':1 if y.ndim==1 else y.shape[1], 'integrated_lufs':loudness(y,sr),
        'rms_p95_p5_db':dr,'relative_silence_ratio':silence,'points':points,'sections':output,
        'definition':'50ms RMS P95/P5 over frames >=5% of maximum RMS; not EBU LRA. LUFS uses pyloudnorm BS.1770.',
        'parameters':{'rms_hop_sec':.05,'relative_gate':.05,'percentiles':[95,5]},
        'section_source':'existing_boundaries_unchanged','limitations':['relative silence is not absolute silence','section loudness may be null for silence or <400ms']}


def onset_statistics(y,sr):
    import librosa
    duration=len(y)/sr;hop=512
    envelope=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop)
    sd=float(envelope.std());mu=float(envelope.mean())
    peaks,_=find_peaks(envelope,height=mu+.5*sd,prominence=max(.5*sd,1e-8),distance=max(1,round(.1*sr/hop)))
    times=peaks*hop/sr;times=times[times<duration]
    windows=[{'start':float(s),'end':float(min(s+8,duration)),
              'events_per_minute':float(np.sum((times>=s)&(times<min(s+8,duration)))*60/(min(s+8,duration)-s))}
              for s in np.arange(0,duration,8)]
    return {'method':'spectral_flux_peaks_v1','count':len(times),'events_per_minute':len(times)*60/duration,
        'events_sec':times.tolist(),'windows':windows,
        'parameters':{'sample_rate':sr,'hop_samples':hop,'threshold_std':.5,'minimum_gap_sec':.1,'window_sec':8},
        'definition':'spectral-flux peaks per minute; includes non-drum attacks, not BPM or a note transcription'}


def check_budget(info):
    from .runner import Unavailable
    estimated=info.frames*info.channels*8*5
    if estimated>2*1024**3:
        raise Unavailable('decoded audio exceeds bounded memory budget; streaming analysis required for this long/high-rate recording')
    if info.frames<info.samplerate*.5 or info.frames>info.samplerate*7200:
        raise ValueError('invalid audio duration')


def measure(path,base,config):
    import soundfile as sf
    import librosa
    from .embedding_cache import audio_sha256
    check_budget(sf.info(str(path)))
    y,sr=sf.read(str(path),always_2d=True,dtype='float32')
    if len(y)<sr*.5 or len(y)>sr*7200 or not np.isfinite(y).all():raise ValueError('invalid audio duration or samples')
    if y.shape[1]>2:raise ValueError('only mono/stereo channel layouts are supported')
    d=dynamics(y[:,0] if y.shape[1]==1 else y,sr,base.get('sections',[]))
    mono=librosa.resample(y.mean(axis=1),orig_sr=sr,target_sr=22050)
    return {'audio_sha256':audio_sha256(path),'method':'dj_acoustic_measurements_v1','dynamics':d,'onsets':onset_statistics(mono,22050)}


def core_features(path,base,config):
    from . import core_source_snapshot as original
    from .features import load_audio
    from .embedding_cache import audio_sha256
    import soundfile as sf
    check_budget(sf.info(str(path)))
    y,sr=load_audio(path);duration=len(y)/sr
    silent=np.max(np.abs(y))<1e-7
    results={}
    def run(name,fn,available=True):
        if not available:
            results[name]={'status':'unavailable','reason':'missing_required_input_or_silent_audio','data':None};return
        try:
            data=fn()
            if name=='tonality' and (not data.get('key_confidence') or not any(v.get('score',0)>0 for v in data.get('candidates',[]))):raise ValueError('original key extractor returned a zero-evidence fallback')
            if name=='timbre' and not any(data.values()):raise ValueError('original extractor returned only fallback zeros')
            results[name]={'status':'ready','data':data}
        except Exception as exc:results[name]={'status':'failed','reason':str(exc),'data':None}
    run('loudness',lambda:original._analyze_loudness(y,sr))
    run('energy',lambda:original._build_energy_curve(y,sr),not silent)
    run('tonality',lambda:original._analyze_key(y,sr),not silent and len(y)>=sr)
    def strict_timbre():
        import logging
        messages=[]
        class Capture(logging.Handler):
            def emit(self,record):messages.append(record.getMessage())
        handler=Capture();original.logger.addHandler(handler)
        try:data=original.timbre_features(str(path),duration)
        finally:original.logger.removeHandler(handler)
        if messages:raise ValueError('original timbre extractor failed: '+messages[-1])
        if data.get('tempogram_peak')==0:data['tempogram_peak']=None
        return data
    run('timbre',strict_timbre,not silent and len(y)>=sr)
    beats=base.get('beats',[]);downbeats=base.get('downbeats',[])
    run('rhythm',lambda:original.rhythm_features(beats,downbeats,duration,base.get('summary',{}).get('bpm')),len(beats)>=4)
    if results['rhythm']['status']=='ready' and not base.get('summary',{}).get('bpm'):
        results['rhythm']['data']['bpm']=None
    if results['rhythm']['status']=='ready' and len(downbeats)<3:
        for k in ['four_on_floor','downbeat_consistency']:results['rhythm']['data'][k]=None
    return {'method':'harbeat_existing_functions_v1','audio_sha256':audio_sha256(path),'source_files':original.SOURCE_HASHES,
        'analysis_sample_rate':sr,'timbre_window_sec':min(30,duration),'timbre_window_start':max(0,(duration-30)/2),
        'definition':'Original HarBeat functions rerun as separate evidence; loudness uses original mono 22050 Hz path. Stereo original-rate measurements are separate.',**results}
