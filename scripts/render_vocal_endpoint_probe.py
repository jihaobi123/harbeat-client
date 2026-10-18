"""Bind frozen experiment sources, then reuse the shared nine-asset renderer."""
import argparse,hashlib,json,pathlib
from render_vocal_bed import render

def bind_and_render(probe,nas,reports):
 d=json.loads((probe/'selection.json').read_text());bound={}
 for t in d['tracks']:
  v=t['provenance'];p=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';m=json.loads(p.read_text());digest=hashlib.sha256(p.read_bytes()).hexdigest()
  if m['track_id']!=t['id'] or m['analysis_run_id']!=v['runId'] or m['assets']['stems']['vocals']['sha256']!=v['vocalSha256']:raise ValueError('frozen source mismatch')
  bound[t['id']]=dict(bassSha256=m['assets']['stems']['bass']['sha256'],manifestSha256=digest)
 for c in d['cases']:c['sourceVerification']={side:bound[c['plan'][key]] for side,key in [('a','from'),('b','to')]}
 selection=probe/'selection-bound.json';selection.write_text(json.dumps(d));render(selection,nas,reports,probe/'audio')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('probe',type=pathlib.Path);p.add_argument('--nas',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/preprocess'));p.add_argument('--reports',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/data/analysis-platform/reports'));a=p.parse_args();bind_and_render(a.probe,a.nas,a.reports)
