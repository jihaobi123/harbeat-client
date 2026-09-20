"""Explicit V2 audition policies on top of the existing immutable pair planner."""
from itertools import permutations
import math,re
from .dj_plan import plan
from .report import digest


def merge(rows):
    result=[]
    for a,b in sorted(rows):
        if b<=a:continue
        if result and a<=result[-1][1]:result[-1][1]=max(b,result[-1][1])
        else:result.append([a,b])
    return result


def vocal_decision(a,b,start,end,pad_sec=.3):
    if a is None or b is None:raise ValueError('unknown vocal intervals cannot be treated as silence')
    if end<=start:raise ValueError('invalid vocal window')
    def clipped(rows,pad):return merge([(max(start,x['start']-pad),min(end,x['end']+pad)) for x in rows])
    aa,bb=clipped(a,pad_sec),clipped(b,pad_sec)
    overlaps=merge([(max(x[0],y[0]),min(x[1],y[1])) for x in aa for y in bb])
    raw=merge([(max(x[0],y[0]),min(x[1],y[1])) for x in clipped(a,0) for y in clipped(b,0)])
    at=sum(y-x for x,y in aa);bt=sum(y-x for x,y in bb);together=sum(y-x for x,y in overlaps)
    present=lambda seconds:seconds>=.5 and seconds/(end-start)>=.05
    return {'triggered':present(at) and present(bt) and together>=.3,'a_active_sec':at,'b_active_sec':bt,
            'a_ratio':at/(end-start),'b_ratio':bt/(end-start),'simultaneous_sec':together,'raw_simultaneous_sec':sum(y-x for x,y in raw),
            'simultaneous_intervals':[{'start':x,'end':y} for x,y in overlaps],
            'parameters':{'pad_playback_sec':pad_sec,'min_active_sec':.5,'min_ratio':.05,'min_simultaneous_sec':.3},
            'definition':'only the audible overlap after tempo mapping; padded VAD proxies, not confirmed lyrics'}


def drum_similarity(a,b):
    # Degraded proxy groups are excluded rather than rewarded by route search.
    keys=('kick','snare_clap','hihat');valid=all(a.get(k,{}).get('status')=='ready' and b.get(k,{}).get('status')=='ready' and a[k].get('pattern_16') and b[k].get('pattern_16') for k in keys)
    if not valid:return {'score':None,'weight':0.,'reason':'missing or degraded drum-pattern evidence'}
    sims=[]
    for k in keys:
        x=a[k]['pattern_16'];y=b[k]['pattern_16']
        if len(x)!=len(y):return {'score':None,'weight':0.,'reason':'incompatible pattern lengths'}
        xx={i for i,z in enumerate(x) if z!='.'};yy={i for i,z in enumerate(y) if z!='.'}
        sims.append(len(xx&yy)/len(xx|yy) if xx|yy else 0.)
    return {'score':sum(sims)/len(sims),'weight':.05,'reason':'ready pattern overlap; heuristic, not a quality verdict'}


def harmonic(a,b):
    x=re.fullmatch(r'(1[0-2]|[1-9])([AB])',str(a or '').upper());y=re.fullmatch(r'(1[0-2]|[1-9])([AB])',str(b or '').upper())
    if not x or not y:return {'score':None,'weight':0.,'reason':'unknown Camelot key'}
    n,m=int(x[1]),int(y[1]);same=x[2]==y[2]
    score=1. if n==m and same else .8 if n==m else .7 if same and (n-m)%12 in (1,11) else 0.
    return {'score':score,'weight':.13,'reason':'Camelot heuristic only'}


def integrated_pair(a,b,meta_a,meta_b,target_bpm=100):
    p=plan(a,b,target_bpm=target_bpm,long_intro_policy='silent_preroll',intro_prefix_policy='silent_preroll')
    if p['status']=='blocked':return p
    start,end=p['entry_sec'],p['handoff_sec'];ma,mb=p['mapping']['a'],p['mapping']['b'];b1=b['roles']['incoming']['end_sec']
    def mapped(c,f):
        raw=c['vocals'].get('intervals')
        return None if raw is None else [{'start':f(v['start']),'end':f(v['end'])} for v in raw]
    decision=vocal_decision(mapped(a,lambda t:t/ma['rate']),mapped(b,lambda t:end+(t-b1)/mb['rate']),start,end)
    p['vocal_overlap']['legacy_section_triggered']=p['vocal_overlap']['rule_triggered']
    p['vocal_overlap']['rule_triggered']=decision['triggered'];p['vocal_decision_v2']=decision
    p['eq']['b_mid_cut_db']=-5 if decision['triggered'] else 0
    p['eq']['definition']='V2 audition: attenuation-only 250–4000Hz band, -5dB only on sustained mapped vocal intersection; linear dB recovery last half-bar'
    p['events']=[e for e in p['events'] if e['name']!='B 中频开始恢复']
    if decision['triggered']:p['events'].insert(-1,{'name':'B 中频开始恢复','planned_sec':p['eq']['restore_start_sec'],'actual_sec':None})
    for i,e in enumerate(p['events']):e['event_id']=f'event_{i+1}'
    p['low_eq']={'cutoff_hz':140,'b_cut_db':-7.,'a_end_cut_db':-9.,'entry_sec':start,'handoff_sec':end,
                 'b_restore_start_sec':p['eq']['restore_start_sec'],'b_restore_end_sec':end,
                 'curve':'linear_dB','definition':'B low band held -7dB then restored during last half-bar; A low band gradually 0 to -9dB over overlap; no boosts'}
    p['policy']['vocal_trigger']='audible_window_presence_and_sustained_mapped_intersection'
    k=harmonic(meta_a.get('camelot'),meta_b.get('camelot'));d=drum_similarity(meta_a.get('drums',{}),meta_b.get('drums',{}))
    tempo=abs(math.log2(ma['source_bpm_local']/mb['source_bpm_local']))*2.6
    casecost={'equal':0.,'a_longer':.08,'b_longer':.18}[p['case']]
    vocalcost=decision['simultaneous_sec']/(end-start)*2.+(.18 if decision['triggered'] else 0.)
    components={'base':1.,'tempo_cost':-tempo,'case_cost':-casecost,'vocal_cost':-vocalcost,'key_bonus':(k['score'] or 0)*k['weight'],'drum_bonus':(d['score'] or 0)*d['weight']}
    p['route_score']={'total':sum(components.values()),'components':components,'key_evidence':k,'drum_evidence':d,
                       'note':'human-defined ranking weights, not measured mixing quality; all songs remain at 100BPM'}
    p['id']=digest({k:v for k,v in p.items() if k!='id'});return p


def rank_routes(count,pairs):
    if not 2<=count<=8:raise ValueError('bounded exhaustive search supports 2 to 8 tracks')
    routes=[]
    for order in permutations(range(count)):
        edges=[pairs[a,b] for a,b in zip(order,order[1:])]
        if any(p['status']=='blocked' for p in edges):continue
        routes.append({'order':list(order),'score':sum(p['route_score']['total'] for p in edges)})
    return sorted(routes,key=lambda r:(-r['score'],r['order']))
