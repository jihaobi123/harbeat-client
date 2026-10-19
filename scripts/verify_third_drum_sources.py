"""Read-only source hashing for the third-track drum audition."""
import argparse,datetime,hashlib,json,pathlib

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def verify(selection,out,nas,reports):
 d=json.loads(selection.read_text())
 for t in d['tracks']:
  v=t['binding'];p=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';m=json.loads(p.read_text());done=json.loads((p.parent/'_SUCCESS.json').read_text())
  if sha(p)!=v['manifestSha256'] or sha(p)!=done['manifest_sha256'] or sha(reports/(t['reportId']+'.json'))!=v['reportSha256'] or m['track_id']!=t['id'] or m['analysis_run_id']!=v['runId']:raise ValueError('source report/manifest changed')
  for field,name in [('masterSha256','master'),('bassSha256','bass'),('vocalSha256','vocals'),('drumSha256','drums')]:
   if field not in v:continue
   a=m['assets']['master'] if name=='master' else m['assets']['stems'][name];path=(nas/a['storage_key']).resolve()
   if nas.resolve() not in path.parents or a['sha256']!=v[field] or sha(path)!=v[field] or a['channels']!=2 or a['sample_rate_hz'] not in ([44100,48000] if name=='master' else [44100]):raise ValueError('actual source changed')
  print('verified',t['title'],flush=True)
 out.write_text(json.dumps(dict(schema='harbeat.third-drum-source-check.v1',selectionSha256=sha(selection),verifiedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),tracks=d['tracks']),indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('selection',type=pathlib.Path);p.add_argument('out',type=pathlib.Path);p.add_argument('--nas',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/preprocess'));p.add_argument('--reports',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/data/analysis-platform/reports'));a=p.parse_args();verify(a.selection,a.out,a.nas,a.reports)
