#!/usr/bin/env python3
"""Attach report-bound, immutable source evidence without changing planner inputs/audio.
Snapshots whitelist analysis values, not private storage paths or credentials.
"""
import argparse, hashlib, json
from pathlib import Path

def sha(b): return hashlib.sha256(b).hexdigest()
def attach(catalog, reports, out, media_base, evidence_base):
    c=json.loads(Path(catalog).read_text())
    for t in c['tracks']:
        raw,r=reports[t['reportId']]
        actual=sha(raw); master=r['documents']['core']['assets']['master']['sha256']
        assert actual==t['provenance']['reportSha256'], f"report identity mismatch {t['title']}"
        assert master==t['provenance']['masterSha256'], f"audio identity mismatch {t['title']}"
        core=r['documents']['core']['analysis']; ext=r.get('extensions',{}); va=r['documents']['vocal_activity']
        genre=ext.get('genre',{}).get('data',{}); vocals=ext.get('dj_signals',{}).get('data',{}).get('vocals',{})
        producer=va.get('producer',{})
        e=dict(schema='harbeat.preprocessing-evidence.v1',reportId=r['id'],reportSha256=actual,masterSha256=master,
            reportSnapshotUrl=evidence_base+actual+'.json',bindingChecks={'reportHash':True,'masterHash':True},
            sections=core['sections'],beatGrid=core['beat_grid'],tempo=core['tempo'],energy=core['energy'],
            vocalActivity={k:va[k] for k in ['intervals','status','needs_review','time_origin','unit','coverage_ratio'] if k in va},
            vocalRms={k:vocals[k] for k in ['points','parameters','asset','source','status','limitations'] if k in vocals},
            genre={k:genre[k] for k in ['top','aggregation','backend','model_files','definition'] if k in genre},
            extensions=[{'name':k,'status':v.get('status','unknown'),'path':'/extensions/'+k} for k,v in ext.items()])
        e['vocalActivity']['source']={k:va.get('source',{}).get(k) for k in ['analysis_run_id','manifest_sha256','track_id','vocal_sha256']}
        e['vocalActivity']['producer']={k:producer[k] for k in ['model','package_version','implementation','model_sha256','backend','parameters'] if k in producer}
        e['vocalRms'].setdefault('points',[])
        target=out/'evidence'/f'{actual}.json';target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(e,ensure_ascii=False,separators=(',',':')))
        t['preprocessing']=e
        for asset in [t['native']]+[a for w in t['windows'] for a in w['variants'].values()]:
            if not asset['url'].startswith(('/','https://','http://')):asset['url']=media_base+asset['url']
    return c

def main():
    p=argparse.ArgumentParser();p.add_argument('--reports',required=True);p.add_argument('--baseline',required=True);p.add_argument('--protected',required=True);p.add_argument('--out',required=True);p.add_argument('--public-base',required=True);args=p.parse_args()
    reports={}
    for f in Path(args.reports).glob('*.json'):
        raw=f.read_bytes();r=json.loads(raw);reports[r['id']]=(raw,r)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    for name,file,media in [('v3-catalog.json',args.baseline,'/analysis-lab-static/v3-live-baseline-20260922/'),('auto-catalog.json',args.protected,'/analysis-lab-static/v3-protected-20260923/')]:
        c=attach(file,reports,out,media,args.public_base.rstrip('/')+'/evidence/')
        (out/name).write_text(json.dumps(c,ensure_ascii=False,separators=(',',':')))
        print(name,len(c['tracks']),'verified reports; decision fields preserved')
if __name__=='__main__':main()
