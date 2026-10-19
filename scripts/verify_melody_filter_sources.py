"""Recheck frozen cached excerpts against their original NAS source bindings."""
import argparse,hashlib,json,pathlib,datetime
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def verify(pack,nas,reports,out):
 d=json.loads(pack.read_text());checked={};cases=[]
 for c in d['cases']:
  bindings={}
  for side,key in [('a','from'),('b','to')]:
   tid=c['plan'][key];v=c['sourceVerification'][side]
   m=nas/'published/tracks'/tid/'runs'/v['runId']/'manifest.json';success=m.parent/'_SUCCESS.json';report=reports/(v['reportId']+'.json')
   if tid not in checked:
    doc=json.loads(m.read_text());done=json.loads(success.read_text())
    if sha(m)!=v['manifestSha256'] or sha(m)!=done['manifest_sha256'] or sha(report)!=v['reportSha256'] or doc['track_id']!=tid or doc['analysis_run_id']!=v['runId']:raise ValueError('report/manifest binding changed')
    for name,expected in [('master',v['masterSha256']),('vocals',v['vocalSha256']),('other',v['otherSha256'])]:
     a=doc['assets']['master'] if name=='master' else doc['assets']['stems'][name];p=(nas/a['storage_key']).resolve()
     if nas.resolve() not in p.parents or a['sha256']!=expected or sha(p)!=expected or a['channels']!=2 or a['sample_rate_hz']!=44100:raise ValueError('actual source changed')
    if doc['assets']['stems']['other']['storage_key']!=v['otherStorageKey']:raise ValueError('other source changed')
    checked[tid]=v;print('verified',tid,flush=True)
   elif checked[tid]!=v:raise ValueError('inconsistent duplicate source evidence')
   bindings[side]=v
  cases.append(dict(id=c['id'],fromTrack=c['plan']['from'],toTrack=c['plan']['to'],bindings=bindings))
 out.write_text(json.dumps(dict(schema='harbeat.melody-filter-source-check.v1',sourcePackSha256=sha(pack),verifiedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceTracks=len(checked),cases=cases),indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('pack',type=pathlib.Path);p.add_argument('out',type=pathlib.Path);p.add_argument('--nas',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/preprocess'));p.add_argument('--reports',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/data/analysis-platform/reports'));a=p.parse_args();verify(a.pack,a.nas,a.reports,a.out)
