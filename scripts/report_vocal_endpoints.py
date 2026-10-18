"""Fuse frozen, source-bound experiment outputs and retain all rejected contexts."""
import argparse,json,pathlib,hashlib
from analysis_platform.vocal_endpoints import detect_endpoints,select_exit

def build(root):
 result=[]
 for c in json.loads((root/'contexts.json').read_text()):
  context=root/(c['id']+'.wav')
  if not context.exists() or hashlib.sha256(context.read_bytes()).hexdigest()!=c['contextSha256']:raise ValueError('context input mismatch')
  modelpath=root/(c['id']+'-model.json');modeldoc=json.loads(modelpath.read_text());doc=json.loads((root/(c['id']+'-frames.json')).read_text())
  binding={k:c[k] for k in ['id','start','end','contextSha256']}
  if not isinstance(doc,dict) or doc.get('context')!=binding or modeldoc.get('context')!=binding or doc.get('modelOutputSha256')!=hashlib.sha256(modelpath.read_bytes()).hexdigest():raise ValueError('stale derived outputs')
  frames=doc['frames'];report=detect_endpoints(frames,c['vad'])
  # Source bar anchors plus local subdivisions; no move of the original DJ cue.
  beat=60/c['bpm'];beats=sorted({round(bar+i*beat,6) for bar in c['bars'] for i in range(4)})
  selected=select_exit(report,c['cueStart'],c['cueEnd'],beats)
  result.append(dict(c,report=report,selected=selected,framesSha256=hashlib.sha256((root/(c['id']+'-frames.json')).read_bytes()).hexdigest(),modelSha256=hashlib.sha256((root/(c['id']+'-model.json')).read_bytes()).hexdigest()))
 out=dict(schema='harbeat.vocal-endpoints-analysis.v1',contexts=result,limitation='Provisional fusion thresholds on isolated stems. No manual boundary ground truth; not a confidence or accuracy claim. Rejected contexts retained.')
 (root/'analysis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 for c in result:print(c['title'],json.dumps(dict(selected=c['selected'],candidates=c['report']['candidates'],rejected=c['report']['rejected']),ensure_ascii=False))
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);build(p.parse_args().root)
