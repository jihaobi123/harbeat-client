"""Explicit audition candidates; never save these as human-reviewed production data."""
import copy
import numpy as np
from .dj_contract import build, source_fingerprint
from .report import digest


def candidate(report):
    original=build(report)
    raw={k:v['raw_sec'] for k,v in original['anchors'].items()}
    if any(v is None for v in raw.values()):raise ValueError('missing structural boundary: '+report['title'])
    if abs(raw['intro_end']-raw['verse_start'])>.001:raise ValueError('intro does not lead to verse')
    bars=np.asarray([x for x in original['grid']['downbeats'] if x<=raw['chorus_end']+3])
    if len(bars)<8:raise ValueError('insufficient measured bar anchors')
    step=float(np.median(np.diff(bars)));indices=np.rint((bars-bars[0])/step);keep=np.ones(len(bars),bool)
    for _ in range(5):
        if sum(keep)<8:raise ValueError('regular-grid fit failed')
        step,offset=np.polyfit(indices[keep],bars[keep],1)
        residual=bars-(offset+step*indices)
        keep=np.abs(residual)<max(.1,3*float(np.median(np.abs(residual))))
    if max(abs(residual[keep]))>.10 or sum(keep)<.8*len(bars):raise ValueError('grid too unstable for fixed-rate preview')
    origin=float(offset%step)
    # Small negative extrapolated pickup is explicitly snapped to source zero.
    if step-origin<.05:origin=0.
    grid_bars=np.arange(origin,original['duration']+1e-6,step).tolist()
    beats=np.arange(origin,original['duration']+1e-6,step/4).tolist()
    anchors={k:min(grid_bars,key=lambda x:abs(x-v)) for k,v in raw.items()}
    anchors['intro_start']=grid_bars[0]
    if max(abs(anchors[k]-raw[k]) for k in raw)>step/2+.05:raise ValueError('boundary too far from preview grid')
    edit={'source_fingerprint':source_fingerprint(report),'anchors':anchors,
          'grid':{'beats':beats,'downbeats':grid_bars,'numerator':4,'denominator':4},'confirmations':{}}
    result=build(report,edit)
    result['grid']['source']='estimated_regular_grid_from_preprocessed_bars'
    for a in result['anchors'].values():a['source']='automatic_preview_snap_not_human_review'
    result['review']={'status':'not_reviewed','revision':0,'current':None}
    result['preview_estimation']={'human_confirmed':False,'method':'robust linear fit to existing bars through first chorus',
        'bpm':240/step,'first_bar_sec':origin,'source_bars':len(bars),'fit_bars':int(sum(keep)),
        'max_inlier_residual_ms':float(max(abs(residual[keep]))*1000),
        'first_recorded_bar_sec':float(bars[0]),
        'adjustments':{k:{'original_sec':raw[k],'candidate_sec':anchors[k],'delta_ms':(anchors[k]-raw[k])*1000} for k in raw},
        'original_issues':{k:v['issues'] for k,v in original['roles'].items()}}
    result['id']=digest({k:v for k,v in result.items() if k!='id'})
    return result
