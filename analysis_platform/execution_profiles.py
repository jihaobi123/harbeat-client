"""Versioned local stem evidence, without pair rendering or model confidence claims.

The analysis uses NumPy/SciPy STFT, band spectral flux and pitch-class folding.
It does not identify a kick/snare instrument or infer a semantic lyric/phrase end.
"""
import math
import numpy as np
from scipy import signal

VERSION = 'harbeat.execution-profile.v1'
STEP = .125


def stem_profile(audio, sr, *, start=0., harmony=True):
    x = np.asarray(audio, dtype=float)
    if x.ndim == 2:
        x = np.mean(x, axis=1)
    n = max(1, round(sr*STEP))
    frames = []
    # RMS activity is relative to this source chunk, with a fixed -70 dB floor.
    rms = [float(np.sqrt(np.mean(x[i:i+n]**2))) for i in range(0,len(x),n)]
    gate = max(10**(-70/20), (np.percentile(rms,95) if rms else 0)*.008)
    for index, i in enumerate(range(0,len(x),n)):
        part = x[i:i+n]
        spectrum = abs(np.fft.rfft(part*np.hanning(len(part)), n=max(8192,len(part))))**2
        frequencies = np.fft.rfftfreq(max(8192,len(part)), 1/sr)
        chroma = None
        if harmony and rms[index] >= gate:
            valid = (frequencies>=55)&(frequencies<=min(5000,sr/2))
            midi = np.rint(69+12*np.log2(frequencies[valid]/440)).astype(int)%12
            folded = np.bincount(midi, weights=spectrum[valid], minlength=12)
            if folded.sum()>1e-12:
                chroma = (folded/folded.sum()).round(6).tolist()
        frames.append({'start':round(start+i/sr,6),'end':round(start+(i+len(part))/sr,6),
                       'rmsDb':round(20*math.log10(max(rms[index],1e-12)),3),
                       'peak':round(float(np.max(abs(part))),6), 'active':bool(rms[index]>=gate),
                       'transient':round(max(0,rms[index]-(rms[index-1] if index else 0)),6),
                       'chroma':chroma})
    return {'frameSeconds':STEP,'activityBasis':'RMS >= max(-70 dBFS, chunk p95 RMS * 0.008); not speech VAD',
            'harmonyBasis':'linear STFT power folded to nearest equal-tempered pitch class; not calibrated key confidence',
            'frames':frames}


def groove_profile(audio, sr, beats, *, start=0.):
    x=np.asarray(audio,dtype=float)
    if x.ndim==2:x=x.mean(axis=1)
    hop=max(1,round(.01*sr));fft=min(2048,max(128,2**int(math.log2(sr*.04))))
    if len(x)<fft or len(beats)<2:
        return {'status':'unknown','events':[],'basis':'insufficient audio or observed beats'}
    frequencies,times,z=signal.stft(x,fs=sr,nperseg=fft,noverlap=fft-hop,boundary='zeros')
    mag=abs(z);events=[]
    for band,low,high in [('low',30,180),('mid',180,2500),('high',2500,min(sr/2,10000))]:
        mask=(frequencies>=low)&(frequencies<high)
        if not mask.any():continue
        flux=np.maximum(0,np.diff(mag[mask],axis=1,prepend=mag[mask,:1])).sum(axis=0)
        scale=float(np.percentile(flux,95))
        if scale<1e-10:continue
        peaks,_=signal.find_peaks(flux,height=scale*.2,prominence=scale*.15,distance=max(1,round(.05*sr/hop)))
        for peak in peaks:
            at=float(times[peak]+start);i=int(np.searchsorted(beats,at,side='right')-1)
            if i<0 or i+1>=len(beats):continue
            interval=beats[i+1]-beats[i]
            if interval<=0:continue
            phase=(at-beats[i])/interval;nearest=round(phase*4)/4
            events.append({'time':round(at,5),'band':band,'beatIndex':i,'phase':round(phase,4),
                           'sixteenth':round(phase*4),'microtimingMs':round((phase-nearest)*interval*1000,2),
                           'strength':round(min(8,float(flux[peak]/scale)),4)})
    return {'status':'ready' if events else 'unknown','events':sorted(events,key=lambda e:e['time']),
            'basis':'10 ms multiband positive spectral flux peaks; within observed beat, quarter-beat nearest subdivision; bands are not drum classes'}


def bar_evidence(track):
    rows=[]
    for index,b in enumerate((track.get('alignment') or {}).get('bars',[])):
        times=list(b.get('beats',[]))+[b.get('end')]
        valid=b.get('valid') is True and len(times)==5 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in times)
        delta=np.diff(times) if valid else []
        usable=bool(valid and all(v>0 for v in delta) and abs(times[0]-b['start'])<.001)
        rows.append({'index':index,'start':b['start'],'end':b['end'],'usable':usable,
                     'intervalRegularity':round(float(max(0,1-np.std(delta)/np.mean(delta))),6) if usable else None,
                     'confidenceKind':'interval regularity heuristic, not calibrated model probability'})
    groups=[]
    sections=track.get('sections') or []
    for count in [8,16]:
        for i in range(len(rows)-count+1):
            span=rows[i:i+count]
            if not all(b['usable'] for b in span) or any(abs(a['end']-b['start'])>.002 for a,b in zip(span,span[1:])):continue
            near=[]
            for section in sections:
                at=section.get('start') if isinstance(section,dict) else None
                if isinstance(at,(int,float)) and abs(at-span[0]['start'])<.5:near.append(section.get('label','unknown'))
            groups.append({'start':span[0]['start'],'end':span[-1]['end'],'bars':count,
                           'sectionBoundaryLabels':near,'musicalPhraseConfidence':None,
                           'basis':'complete contiguous four-beat bars; section boundary is supporting evidence only'})
    return {'bars':rows,'longWindows':groups,'beatModelComparison':'unknown; upstream model activations not published'}


def _summary(profile, stem, start, end):
    frames=((profile.get('stems') or {}).get(stem) or {}).get('frames',[])
    frames=[f for f in frames if f['start']<end and f['end']>start]
    if not frames or end<=start:return None,None
    cursor=start;power=0.;pitch=np.zeros(12);pitch_weight=0.
    for frame in frames:
        left,right=max(start,frame['start']),min(end,frame['end'])
        if left>cursor+.001 or right<=left:return None,None
        width=max(0,right-max(left,cursor));value=10**(frame['rmsDb']/10)
        if not math.isfinite(value):return None,None
        power+=value*width;cursor=max(cursor,right)
        if frame.get('chroma') is not None:
            values=np.asarray(frame['chroma'],dtype=float)
            if len(values)!=12 or not np.isfinite(values).all() or (values<0).any():return None,None
            pitch+=values*value*width;pitch_weight+=value*width
    if cursor<end-.001:return None,None
    return math.sqrt(power/(end-start)),pitch/pitch_weight if pitch_weight>0 else None


def compare_profiles(a,b,start_a,start_b,duration,rate):
    result={'stemAvailable':{},'vocalBenefit':0.,'vocalSafe':False,
            'basis':'precomputed local stem RMS and pitch-class summary; provisional, no rendered output statistics'}
    for stem in ['bass','other','vocals']:
        aa,ac=_summary(a,stem,start_a,start_a+duration);bb,bc=_summary(b,stem,start_b,start_b+duration*rate)
        result['stemAvailable'][stem]=aa is not None and bb is not None
        if stem!='vocals':
            scores=[]
            if aa is not None and bb is not None:
                for at in np.arange(0,duration,STEP):
                    left,_=_summary(a,stem,start_a+at,start_a+min(duration,at+STEP))
                    right,_=_summary(b,stem,start_b+at*rate,start_b+min(duration,at+STEP)*rate)
                    if left is None or right is None:continue
                    if min(left,right)<10**(-45/20):scores.append(0.);continue
                    progress=min(1,(at+STEP/2)/duration);x=left*(1-progress);y=right*progress
                    scores.append(2*min(x,y)/(x+y+1e-12))
            result[stem+'Overlap']=float(np.clip(np.mean(scores),0,1)) if scores else None
            result[stem+'Difference']=None if ac is None or bc is None else float(np.clip(1-np.dot(ac,bc)/max(np.linalg.norm(ac)*np.linalg.norm(bc),1e-12),0,1))
    return result


def local_pair_evidence(a,b,start_a,start_b,duration,rate):
    """Measured local proxies, kept separate from subjective suitability scores."""
    left=((a.get('groove') or {}).get('events') or [])
    right=((b.get('groove') or {}).get('events') or [])
    left=[e for e in left if start_a<=e['time']<start_a+duration]
    right=[e for e in right if start_b<=e['time']<start_b+duration*rate]
    rhythm={'status':'unknown','timingMedianMs':None,'timingP95Ms':None,'histogramCosine':None,
            'basis':'same-band nearest onset distance and 32-bin normalized-overlap-time histogram; not perceived groove compatibility'}
    if len(left)>=4 and len(right)>=4:
        distances=[];vectors=[]
        for events,start,scale in [(left,start_a,1),(right,start_b,rate)]:
            vector=np.zeros((3,32))
            for event in events:
                if event['band'] not in ['low','mid','high']:continue
                band=['low','mid','high'].index(event['band'])
                slot=min(31,int((event['time']-start)/scale/duration*32))
                vector[band,slot]+=min(8,event['strength'])
            vectors.append(vector.ravel())
        for source,target,ss,ts,sr,tr in [(left,right,start_a,start_b,1,rate),(right,left,start_b,start_a,rate,1)]:
            for event in source:
                times=[(other['time']-ts)/tr for other in target if other['band']==event['band']]
                if times:distances.append(min(abs((event['time']-ss)/sr-value) for value in times)*1000)
        norms=np.linalg.norm(vectors[0])*np.linalg.norm(vectors[1])
        if distances and norms>0:
            rhythm.update(status='ready',timingMedianMs=round(float(np.median(distances)),2),
                          timingP95Ms=round(float(np.percentile(distances,95)),2),
                          histogramCosine=round(float(np.dot(*vectors)/norms),6))
    harmony={}
    for stem in ['bass','other']:
        differences=[];observations=0
        for at in np.arange(0,duration,STEP):
            aa,ac=_summary(a,stem,start_a+at,start_a+min(duration,at+STEP))
            bb,bc=_summary(b,stem,start_b+at*rate,start_b+min(duration,at+STEP)*rate)
            if aa is None or bb is None:continue
            observations+=1
            if min(aa,bb)<10**(-45/20) or ac is None or bc is None:continue
            differences.append(float(np.clip(1-np.dot(ac,bc)/max(np.linalg.norm(ac)*np.linalg.norm(bc),1e-12),0,1)))
        harmony[stem]={'audibleComparedFrames':len(differences),'observedFrames':observations,
                       'meanPitchDifference':round(float(np.mean(differences)),6) if differences else None,
                       'p95PitchDifference':round(float(np.percentile(differences,95)),6) if differences else None,
                       'basis':'local pitch-class cosine distance when both stems exceed -45 dBFS; no chord dissonance claim'}
    return {'rhythm':rhythm,'harmony':harmony,'longBlendApproved':False,
            'limitations':['These are measured proxies. No universal suitability threshold or long-overlap listening calibration has been established.']}
