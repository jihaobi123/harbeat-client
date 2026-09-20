"""Time-weighted descriptive statistics of an existing DEAM curve."""
import math
import numpy as np
from .report import digest, intervals


def summarize(points,sections,duration):
    valid=[];cursor=0.
    for p in sorted(points,key=lambda p:p.get('start',0)):
        if not all(isinstance(p.get(k),(float,int)) and math.isfinite(p[k]) for k in ['start','end','valence','arousal']):continue
        start,end=max(cursor,0.,p['start']),min(duration,p['end'])
        if end<=start:continue
        valid.append({**p,'start':start,'end':end});cursor=end
    weights=np.array([p['end']-p['start'] for p in valid]);covered=float(weights.sum())
    out={'covered_seconds':covered,'coverage_ratio':covered/duration if duration else 0,'point_count':len(valid)}
    for key in ['valence','arousal']:
        values=np.array([p[key] for p in valid]);mean=float(np.average(values,weights=weights)) if covered else None
        out[key+'_mean']=mean
        out[key+'_std']=float(np.sqrt(np.average((values-mean)**2,weights=weights))) if covered else None
        out[key+'_range']=float(np.ptp(values)) if covered else None
    state=0;last_end=None;switches=0;observed_transition_seconds=0.
    for p in valid:
        contiguous=last_end is not None and abs(p['start']-last_end)<1e-6
        if not contiguous:state=0
        if contiguous:observed_transition_seconds+=p['end']-p['start']
        new=1 if p['valence']>=.12 else -1 if p['valence']<=-.12 else state
        if state and new!=state:switches+=1
        state=new;last_end=p['end']
    out.update(polarity_switches=switches,polarity_switches_per_minute=switches*60/covered if covered else None)
    out['sections']=[{**s,**summarize([{**p,'start':max(s['start'],p['start'])-s['start'],'end':min(s['end'],p['end'])-s['start']} for p in valid if p['start']<s['end'] and p['end']>s['start']],[],s['end']-s['start'])} for s in intervals(sections)]
    return out


def derive(path,base,config):
    from .runner import Unavailable
    source=base.get('extensions',{}).get('emotion',{})
    if source.get('status')!='ready' or not source.get('data',{}).get('points'):raise Unavailable('需要已完成、同曲的 DEAM 情绪曲线')
    data=source['data']
    if data.get('audio_sha256') and data['audio_sha256']!=base.get('audio_sha256'):raise Unavailable('情绪曲线与当前音频指纹不一致')
    duration=float(base.get('summary',{}).get('duration') or data.get('duration') or 0)
    if duration<=0:raise Unavailable('缺少曲目时长')
    return {'method':'deam_time_weighted_summary_v1','source_emotion_sha256':digest(source),
        'audio_sha256':base.get('audio_sha256'),**summarize(data['points'],base.get('sections',[]),duration),
        'definition':'Time-weighted DEAM summaries over display intervals; gaps reset polarity state. Not emotional depth or listener response.',
        'parameters':{'polarity_hysteresis':.12,'switch_rate_denominator':'covered_seconds'}}
