"""Independent waveform checks. Acoustic evidence never certifies section semantics."""
from pathlib import Path
import hashlib,json
import numpy as np
from scipy.signal import find_peaks


def distances(points,targets):
    points=np.asarray(points,float);targets=np.asarray(targets,float)
    if not len(points) or not len(targets):return np.full(len(points),np.inf)
    positions=np.searchsorted(targets,points)
    return np.minimum(abs(points-targets[np.clip(positions-1,0,len(targets)-1)]),abs(points-targets[np.clip(positions,0,len(targets)-1)]))


def grid_metrics(ticks,onsets,duration):
    ticks=np.asarray(ticks,float);ticks=ticks[(ticks>=.1)&(ticks<=duration-.1)]
    d=distances(ticks,onsets)
    if not len(ticks) or not len(onsets):return {'status':'insufficient_evidence','count':len(ticks),'coverage_50ms':0.,'median_nearest_onset_ms':None,'capped_mean_ms':None}
    return {'status':'measured','count':len(ticks),'coverage_50ms':float(np.mean(d<=.05)),
            'median_nearest_onset_ms':float(np.median(d)*1000),'capped_mean_ms':float(np.mean(np.minimum(d,.25))*1000),
            'note':'distance to a detected transient; rests and syncopation are not beat errors'}


def compare_grids(platform,colleague,onsets,duration):
    a=grid_metrics(platform,onsets,duration);b=grid_metrics(colleague,onsets,duration);winner='inconclusive'
    if a['status']==b['status']=='measured' and min(a['count'],b['count'])>=16:
        # Require both a clear coverage advantage and a timing advantage, not sub-hop rounding.
        for name,left,right in [('platform',a,b),('colleague',b,a)]:
            if left['coverage_50ms']-right['coverage_50ms']>=.08 and right['capped_mean_ms']-left['capped_mean_ms']>=10:winner=name
    return {'platform':a,'colleague':b,'winner':winner,'human_confirmed':False,'semantic_section_verified':False,
            'decision_rule':'at least 16 beats; coverage advantage >=8 percentage points AND capped mean distance advantage >=10ms',
            'limitation':'onset proximity compares timing evidence only, not downbeat phase or section identity'}


def extract_features(source,end_sec,cache):
    import librosa
    source=Path(source);cache=Path(cache);fingerprint=hashlib.sha256(source.read_bytes()).hexdigest()
    params={'version':1,'sample_rate':22050,'hop':220,'fft':1024,'end_sec':float(end_sec),'method':'positive log-magnitude spectral flux; low/mid/high bands; adjacent log-mel feature changes'}
    key=hashlib.sha256(json.dumps([fingerprint,params],sort_keys=True).encode()).hexdigest();path=cache/(key+'.json')
    if path.exists():return json.loads(path.read_text())
    y,sr=librosa.load(source,sr=22050,duration=end_sec,mono=True)
    hop=params['hop'];spec=np.abs(librosa.stft(y,n_fft=1024,hop_length=hop,center=True));freq=librosa.fft_frequencies(sr=sr,n_fft=1024)
    flux=np.maximum(np.diff(np.log1p(spec*10),axis=1,prepend=np.log1p(spec[:,:1]*10)),0)
    times=np.arange(spec.shape[1])*hop/sr
    components=[]
    for lo,hi in [(30,180),(180,2000),(2000,9000)]:
        v=np.mean(flux[(freq>=lo)&(freq<hi)],axis=0);scale=np.percentile(v,95);components.append(v/max(scale,1e-8))
    envelope=np.mean(components,axis=0)
    peaks,_=find_peaks(envelope,distance=max(1,round(.09*sr/hop)),prominence=max(.06,float(np.percentile(envelope,75)*.2)),height=max(.08,float(np.percentile(envelope,65))))
    # STFT frames are center-timed; no guessed VAD or model latency offset is subtracted.
    mel=librosa.feature.melspectrogram(S=spec**2,sr=sr,n_mels=32,fmin=30,fmax=9000)
    feat=np.log1p(mel);mu=np.mean(feat,axis=1,keepdims=True);sd=np.std(feat,axis=1,keepdims=True);feat=(feat-mu)/np.maximum(sd,.05)
    novel=[];nt=[]
    for t in np.arange(1.5,float(times[-1])-1.5,.1):
        k=round(t*sr/hop);w=round(1.5*sr/hop)
        novel.append(float(np.mean((np.mean(feat[:,k:k+w],axis=1)-np.mean(feat[:,k-w:k],axis=1))**2)));nt.append(float(t))
    scale=max(np.percentile(novel,95),1e-8);novel=(np.asarray(novel)/scale).tolist()
    data={'audio_sha256':fingerprint,'parameters':params,'duration':len(y)/sr,'onsets':[float(times[k]) for k in peaks],
          'onset_strengths':[float(envelope[k]) for k in peaks],'novelty_times':nt,'novelty':novel,
          'limitations':['Full-master transients include non-drum sounds.','Feature change peaks locate acoustic changes, not intro/verse/chorus labels.','No independent annotated reference; these are proxy diagnostics, not accuracy percentages.']}
    cache.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,allow_nan=False));return data


def boundary_evidence(name,platform_time,colleague_time,features,bar_sec):
    nt=np.asarray(features['novelty_times']);nv=np.asarray(features['novelty']);mask=(nt>=max(1.5,platform_time-2*bar_sec))&(nt<=platform_time+2*bar_sec)
    local,_=find_peaks(nv,distance=10);peaks=[int(i) for i in local if mask[i]];peaks=sorted(peaks,key=lambda i:nv[i],reverse=True)[:3]
    def row(t):
        return {'time_sec':t,'nearest_transient_ms':float(distances([t],features['onsets'])[0]*1000) if features['onsets'] else None,
                'acoustic_change':float(np.interp(t,nt,nv)) if len(nt) else None}
    return {'name':name,'platform':row(platform_time),'colleague':row(colleague_time),'delta_ms':(colleague_time-platform_time)*1000,
            'nearby_acoustic_changes':[{'time_sec':float(nt[i]),'strength':float(nv[i])} for i in peaks],
            'semantic_winner':'unverifiable_without_reference','review_required':True}
