"""Experimental isolated-vocal endpoint policy. Thresholds are not calibrated accuracy.
All times are source seconds. Coarse classifiers corroborate activity, not fine boundaries.
"""
import math

PARAMETERS = dict(frameSeconds=.05, breathGap=.30, tailMaximum=1.20,
                  quietConfirm=.25, safetyPad=.08, modelVoice=.80, pitchProbability=.50)

def detect_endpoints(frames, vad):
    if not frames or len(frames)<3 or any(not all(math.isfinite(x[k]) for k in ['t','rms','voiced','voice']) or x['rms']<0 for x in frames):
        raise ValueError('finite source-bound frames required')
    if any(b['t']<=a['t'] for a,b in zip(frames,frames[1:])) or any(len(x)!=2 or not all(math.isfinite(v) for v in x) or x[1]<=x[0] for x in vad):
        raise ValueError('ordered frames and valid VAD intervals required')
    dt=frames[1]['t']-frames[0]['t']
    if any(abs(b['t']-a['t']-dt)>.001 for a,b in zip(frames,frames[1:])):raise ValueError('uniform frames required')
    levels=sorted(x['rms'] for x in frames); high=levels[int(.95*(len(levels)-1))]
    strong=max(high*.08,10**(-55/20)); low=max(high*.008,10**(-70/20))
    seed=[(x['rms']>=strong and (any(a<=x['t']<b for a,b in vad) or x['voice']>=PARAMETERS['modelVoice'])) or (x['rms']>=low and x['voiced']>=PARAMETERS['pitchProbability'] and x['voice']>=PARAMETERS['modelVoice']) for x in frames]
    spans=[]
    for i,on in enumerate(seed):
        if on:
            if spans and frames[i]['t']-frames[spans[-1][1]]['t']<=PARAMETERS['breathGap']+dt+1e-6:spans[-1][1]=i
            else:spans.append([i,i])
    candidates=[];rejected=[]
    for n,(a,b) in enumerate(spans):
        if (b-a+1)*dt<.15:continue
        seed_end=frames[b]['t']+dt;tail=b+1;unsettled=False
        # Fine support is local to a confirmed span, and uses a lower amplitude gate.
        while tail<len(frames):
            x=frames[tail]
            support=x['rms']>=low and (x['voiced']>=PARAMETERS['pitchProbability'] or x['rms']>=strong*.35)
            if not support:break
            if x['t']-seed_end>=PARAMETERS['tailMaximum']:
                unsettled=True;break
            tail+=1
        end=frames[min(tail,len(frames)-1)]['t']
        # Quiet unvoiced words and later soft phrases may evade energy/pitch gates.
        overlapping=[v for v in vad if v[0]<seed_end and v[1]>frames[a]['t']]
        vad_end=max([v[1] for v in overlapping],default=end)
        if vad_end-seed_end>PARAMETERS['tailMaximum']:unsettled=True
        end=max(end,vad_end)
        next_seed=frames[spans[n+1][0]]['t'] if n+1<len(spans) else frames[-1]['t']
        later_vad=[v[0] for v in vad if v[0]>=seed_end and v[0]>frames[a]['t']]
        next_onset=min([next_seed]+later_vad)
        next_observed=next_onset<frames[-1]['t']-.001 and (n+1<len(spans) or bool(later_vad))
        # Any nearby quiet pitched frame protects the tail; classifier score alone is too coarse.
        quiet_start=max(tail,math.ceil((end-frames[0]['t'])/dt-1e-6))
        for j in range(quiet_start,min(len(frames),quiet_start+int(PARAMETERS['quietConfirm']/dt)+1)):
            x=frames[j]
            if x['rms']>=low and (x['voiced']>=.5 or x['rms']>=strong*.35):
                unsettled=True
        item=dict(start=frames[a]['t'],seedEnd=seed_end,tailEnd=end,
                  nextOnset=next_onset,nextOnsetObserved=next_observed,gap=next_onset-end)
        if unsettled:rejected.append(dict(item,reason='tail-unsettled'))
        elif item['gap']<PARAMETERS['quietConfirm']:rejected.append(dict(item,reason='gap-too-short'))
        else:candidates.append(item)
    return dict(parameters=PARAMETERS,thresholds=dict(strongRms=strong,tailRms=low),candidates=candidates,rejected=rejected,
                status='experimental-listening-review-required')

def select_exit(report, cue_start, cue_end, beats, fade=.20):
    if not all(math.isfinite(x) for x in [cue_start,cue_end,fade]) or cue_end<=cue_start or fade<=0:raise ValueError('invalid cue')
    options=[]
    for c in report['candidates']:
        if c['seedEnd']<max(cue_start,cue_end-3) or c['tailEnd']>=cue_end or c['nextOnset']<cue_end+.08:continue
        safe=c['tailEnd']+.08
        aligned=next((x for x in sorted(beats) if math.isfinite(x) and x>=safe and x+fade<=min(cue_end,c['nextOnset']-.08)),None)
        if aligned is not None:options.append(dict(c,fadeStart=aligned,fadeEnd=aligned+fade,beatAligned=True))
    return max(options,key=lambda x:x['tailEnd']) if options else None
