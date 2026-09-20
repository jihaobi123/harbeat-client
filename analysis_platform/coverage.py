"""Latest-report coverage. Presence is never called prediction accuracy."""
from collections import Counter


def latest_reports(store):
    items=store.reports()
    formal=[r for r in items if r.get('audio',{}).get('catalog_track_id')]
    seen=set();out=[]
    for r in formal or items:
        key=r.get('audio',{}).get('catalog_track_id') or r.get('audio',{}).get('sha256') or r['id']
        if key in seen:continue
        seen.add(key);out.append(store.get_report(r['id']))
    return out


def missing_modules(report,modules):
    out=[]
    for name in modules:
        item=report.get('extensions',{}).get(name,{})
        partial=name=='core_features' and any(isinstance(v,dict) and v.get('status')=='failed' for v in (item.get('data') or {}).values())
        if item.get('status')!='ready' or partial:out.append(name)
    return out


def counts(reports):
    from .runner import MODULES
    result={name:dict(Counter(r['extensions'].get(name,{}).get('status','missing') for r in reports)) for name in MODULES}
    core={name:dict(Counter(r['extensions'].get('core_features',{}).get('data',{}).get(name,{}).get('status','missing') if r['extensions'].get('core_features',{}).get('data') else 'missing' for r in reports)) for name in ['loudness','energy','tonality','timbre','rhythm']}
    return {'tracks':len(reports),'modules':result,'core_submodules':core,'definition':'Newest report per catalog track; computed coverage, not accuracy. Core input gaps and failures counted separately.'}
