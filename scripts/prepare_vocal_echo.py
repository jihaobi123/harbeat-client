"""Create a finite wet-only clip and eligibility sidecar; never overwrite source packs."""
import argparse,hashlib,json,pathlib
import numpy as np
import soundfile as sf
from scripts.report_vocal_endpoints import verified_analysis
from scripts.prepare_vocal_endpoint_pack import validate_handover_sources
from analysis_platform.stem_effects import plan_vocal_echo,render_vocal_echo

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(root,web,out):
 analysis=verified_analysis(root/'probe-talgo');original=verified_analysis(root)
 sourcepack=root/'pack/vocal-endpoints-data.json'
 if not sourcepack.exists():sourcepack=root/'pack.json'
 pack=json.loads(sourcepack.read_text());cases=[];audit=[]
 for old in pack['cases']:
  c=dict(old);p=c['plan'];a=next(t for t in analysis['contexts'] if t['id']==p['from']);b=next(t for t in analysis['contexts'] if t['id']==p['to'])
  validate_handover_sources(c,a,b)
  expected={k:round(a['selected'][k]-p['start'],9) for k in ['tailEnd','nextOnset','fadeStart','fadeEnd']}
  if c['endpoint']!=expected:raise ValueError('frozen dry endpoint differs from fresh source evidence')
  fx=plan_vocal_echo(c,a,b)
  assets={k:dict(v) for k,v in c['assets'].items()}
  for key,asset in assets.items():
   src=web/asset['url'].lstrip('/')
   if not src.is_file() or sha(src)!=asset['sha256'] or src.stat().st_size!=asset['bytes']:raise ValueError('shared asset mismatch '+key)
  src=web/assets['aVocal']['url'].lstrip('/');pcm,sr=sf.read(src,dtype='float32',always_2d=True)
  if sr!=44100 or pcm.shape!=(round((c['pre']+p['duration'])*sr),2):raise ValueError('fixed A vocal format mismatch')
  wet=render_vocal_echo(pcm,sr,fx);peak=float(np.max(np.abs(wet)))
  if not .00001<peak<=.70:raise ValueError('wet signal silent or above declared isolated-peak bound')
  out.mkdir(parents=True,exist_ok=True);audio=web/'vocal-echo-audio';audio.mkdir(exist_ok=True);target=audio/'vocal-echo-01-aEcho.wav';sf.write(target,wet,sr,subtype='FLOAT')
  asset=dict(url='/vocal-echo-audio/'+target.name,sha256=sha(target),bytes=target.stat().st_size,duration=len(wet)/sr,frames=len(wet),channels=2,sampleRate=sr,peak=peak)
  assets['aEcho']=asset;c.update(id='vocal-echo-01',sourceCaseId=old['id'],assets=assets,fx=fx)
  c['evidence']=dict(c['evidence'],analysis=a,control=b,selected=a['selected'])
  c['fxEvidence']=dict(inputVocalSha256=assets['aVocal']['sha256'],wetSha256=asset['sha256'],isolatedWetPeak=peak,isolatedWetRms=float(np.sqrt(np.mean(wet.astype('float64')**2))),analysisSha256=sha(root/'probe-talgo/analysis.json'),detectorImplementation=analysis['implementation'],window=fx,normalization='none; both arms share dry/output gains',status='controlled-audition-only; no human quality or lyric certification')
  cases.append(c)
 for t in original['contexts']:
  if not t['selected']:audit.append(dict(title=t['title'],eligible=False,reason=t['selectionAudit']['reason']))
 identity=json.dumps(dict(sourcePackSha256=sha(sourcepack),analysisSha256=sha(root/'probe-talgo/analysis.json'),effectImplementation=sha(pathlib.Path(__file__).parents[1]/'analysis_platform/stem_effects.py'),cases=[dict(id=c['id'],fx=c['fx'],assets=c['assets']) for c in cases]),sort_keys=True).encode()
 result=dict(schema='harbeat.vocal-echo-pack.v1',selectionSha256=hashlib.sha256(identity).hexdigest(),cases=cases,audit=audit,sourcePackSha256=sha(sourcepack),limitation='One frozen pair; only outgoing vocal wet effect differs. Source hash and finite quiet-window checks are not validated perceptual or lyric-end accuracy.')
 raw=json.dumps(result,ensure_ascii=False,indent=2)+'\n';(web/'vocal-echo-data.json').write_text(raw);(out/'pack.json').write_text(raw);(out/'fx-window.json').write_text(json.dumps(cases[0]['fxEvidence'],indent=2)+'\n')
 print('ready',[(c['aTitle'],c['bTitle'],c['fx']['sendStart'],c['fx']['wetEnd'],c['assets']['aEcho']['peak']) for c in cases])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);p.add_argument('web',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);a=p.parse_args();prepare(a.root,a.web,a.output)
