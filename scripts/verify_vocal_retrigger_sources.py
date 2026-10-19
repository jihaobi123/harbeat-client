import argparse,datetime,hashlib,json,pathlib
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(1024*1024),b''):h.update(x)
 return h.hexdigest()
def verify(selection,out,nas,reports):
 d=json.loads(selection.read_text());tracks=[]
 for t in d['tracks']:
  v=t['binding'];path=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';m=json.loads(path.read_text());success=json.loads((path.parent/'_SUCCESS.json').read_text())
  if sha(path)!=v['manifestSha256'] or sha(path)!=success['manifest_sha256'] or sha(reports/(t['reportId']+'.json'))!=v['reportSha256'] or m['track_id']!=t['id'] or m['analysis_run_id']!=v['runId']:raise ValueError('source report/manifest mismatch')
  for key,expected in [('master',v['masterSha256']),('vocals',v['vocalSha256']),('bass',v['bassSha256'])]:
   a=m['assets']['master'] if key=='master' else m['assets']['stems'][key];p=(nas/a['storage_key']).resolve()
   if nas.resolve() not in p.parents or a['sha256']!=expected or sha(p)!=expected or a['channels']!=2 or a['sample_rate_hz']!=44100:raise ValueError('actual source changed')
  tracks.append(t);print('verified',t['title'],flush=True)
 out.write_text(json.dumps(dict(schema='harbeat.vocal-retrigger-source-check.v1',selectionSha256=sha(selection),verifiedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),tracks=tracks),indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('selection',type=pathlib.Path);p.add_argument('out',type=pathlib.Path);p.add_argument('--nas',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/preprocess'));p.add_argument('--reports',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/data/analysis-platform/reports'));a=p.parse_args();verify(a.selection,a.out,a.nas,a.reports)
