"""Freeze whole-activity candidates, reject unsupported cases and package one-shot."""
import argparse,copy,json,pathlib,hashlib,shutil
import numpy as np
import soundfile as sf
from analysis_platform.vocal_retrigger import plan_retrigger,capture_phrase
from scripts.report_vocal_endpoints import verified_analysis
from scripts.prepare_vocal_endpoint_pack import validate_handover_sources
from scripts.prepare_melody_filter import checked_asset
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def select(root,parent,details):
 frozen=json.loads((root/'frozen-input.json').read_text())
 if sha(parent/'pack.json')!=frozen['sourcePackSha256']:raise ValueError('frozen parent changed')
 reports=[]
 for v in frozen['analysisSources']:
  p=pathlib.Path(v['path'])
  if sha(p/'analysis.json')!=v['sha256']:raise ValueError('source observations changed')
  reports.append(verified_analysis(p))
 tracks={json.loads(p.read_text())['track']['id']:json.loads(p.read_text())['track'] for p in details.glob('*.json')};old=json.loads((parent/'pack.json').read_text());cases=[];audit=[];used={}
 for i,c in enumerate(old['cases']):
  a,b=c['evidence']['analysis'],c['evidence']['control'];row=dict(sourceCaseId=c['id'],pair=[c['aTitle'],c['bTitle']],accepted=False)
  if not any(a in r['contexts'] and b in r['contexts'] for r in reports):raise ValueError('case observations are not frozen verified outputs')
  validate_handover_sources(c,a,b)
  try:fx=plan_retrigger(c,a,b)
  except ValueError as e:row['reason']=str(e);audit.append(row);continue
  p=c['plan'];x={k:copy.deepcopy(c[k]) for k in ['aTitle','bTitle','bpm','pre','post','plan','sourceVerification','baselineBass']};x.update(id='vocal-retrigger-'+str(i+1).zfill(2),sourceCaseId=c['id'],originalPlanSha256=c['planSha256'],planSha256=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(),planHashEncoding='Python canonical sorted JSON',fx=fx,originalAssets={k:v for k,v in c['assets'].items() if k in ['aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal']},vocalEvidence=dict(analysis=a,control=b),originalVocalConflictPolicy='unchanged frozen5197reference; new300ms-protected replay support added')
  for side,key in [('a','from'),('b','to')]:
   t=tracks[p[key]];v=c['sourceVerification'][side]
   if any(t['provenance'][k]!=v[k] for k in ['masterSha256','vocalSha256','reportSha256','runId']):raise ValueError('track snapshot/source mismatch')
   used[t['id']]=dict(id=t['id'],title=t['title'],reportId=t['reportId'],binding=v)
  cases.append(x);row.update(accepted=True,reason='complete provisional activity segment fits source-bound quiet coverage; human cut review pending',fx=fx);audit.append(row)
 if not cases:raise ValueError('no eligible whole-segment candidate; original cues unchanged')
 out=dict(schema='harbeat.vocal-retrigger-selection.v1',sourcePackSha256=frozen['sourcePackSha256'],cases=cases,tracks=list(used.values()),audit=audit);(root/'selection.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print([(r['pair'],r['accepted'],r['reason']) for r in audit])
def package(root,web):
 selection=json.loads((root/'selection.json').read_text());proof=json.loads((root/'source-check.json').read_text());output=web/'vocal-retrigger-audio';output.mkdir(exist_ok=True);cases=[]
 if proof['selectionSha256']!=sha(root/'selection.json'):raise ValueError('NAS proof bound to another selection')
 for c in selection['cases']:
  c=copy.deepcopy(c);assets={};decoded={}
  for side,key in [('a','from'),('b','to')]:
   row=next(x for x in proof['tracks'] if x['id']==c['plan'][key])
   if row['binding']!=c['sourceVerification'][side]:raise ValueError('fresh source proof mismatch')
  for key,a in c['originalAssets'].items():
   duration=c['pre']+c['plan']['duration'] if key.startswith('a') else c['plan']['duration'] if key.startswith('bEntry') else c['post'];src=checked_asset(web,a,duration);dst=output/(c['id']+'-'+key+src.suffix);shutil.copy2(src,dst);assets[key]=dict(a,url='/vocal-retrigger-audio/'+dst.name)
   if key=='aVocal':decoded[key]=sf.read(src,dtype='float32',always_2d=True)[0]
  fx=c['fx'];pcm=decoded['aVocal'];shot=capture_phrase(pcm,44100,c,fx);lo=round((fx['contextStart']-fx['sourceOrigin'])*44100);hi=round((fx['contextEnd']-fx['sourceOrigin'])*44100)
  for key,x in [('aOneShot',shot),('aReviewContext',pcm[lo:hi])]:
   dst=output/(c['id']+'-'+key+'.wav');sf.write(dst,x,44100,subtype='FLOAT');assets[key]=dict(url='/vocal-retrigger-audio/'+dst.name,sha256=sha(dst),bytes=dst.stat().st_size,duration=len(x)/44100,frames=len(x),sampleRate=44100,channels=2,peak=float(np.max(abs(x))))
  if not 1e-5<assets['aOneShot']['peak']<.75:raise ValueError('one-shot silent or excessive isolated peak')
  c['assets']=assets;c['captureEvidence']=dict(inputVocalSha256=assets['aVocal']['sha256'],oneShotSha256=assets['aOneShot']['sha256'],contextSha256=assets['aReviewContext']['sha256'],captureGainPolicy=fx['captureGainPolicy'],sourceSamples=[round((fx['sourceStart']-fx['sourceOrigin'])*44100),round((fx['sourceEnd']-fx['sourceOrigin'])*44100)],humanCutStatus='pending',normalization='none');c.pop('originalAssets');cases.append(c)
 code={f:sha(web/'src/vocal-retrigger'/f) for f in ['policy.ts','graph.ts','transport.ts','rounds.ts']};identity=dict(selectionSha256=sha(root/'selection.json'),sourceCheckSha256=sha(root/'source-check.json'),preparerSha256=sha(pathlib.Path(__file__)),plannerSha256=sha(pathlib.Path(__file__).parents[1]/'analysis_platform/vocal_retrigger.py'),playbackSourceSha256=code,imports={p:sha(web/p) for p in ['src/vocal-bridge/automation.ts','src/v30/eq.ts','src/realtime/cache.ts','public/vocal-echo-clock.js']},cases=[dict(id=c['id'],planSha256=c['planSha256'],assets=c['assets'],fx=c['fx']) for c in cases])
 pack=dict(schema='harbeat.vocal-retrigger-pack.v1',selectionSha256=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),sourcePackSha256=selection['sourcePackSha256'],cases=cases,audit=selection['audit'],rendering='Identical six cached dry clips, original master/vocal gain/EQ/source schedule; optional single original-gain captured A phrase at native Bbody handoff. No normalization or other treatment.',limitation='One provisional selected endpoint candidate inside a longer continuous VAD/rejected interval; not a complete activity interval or certified lyric/word boundary. Human context/sample review required before formalAB. Two fixed-cue cases skipped, not negative listening results. This tests one-shot only, not repeated loops/wordchops/livehotkeys. Inherited cachedatempo/sourceedges shared; no nativebitexact claim.')
 raw=json.dumps(pack,ensure_ascii=False,indent=2)+'\n';(root/'pack.json').write_text(raw);(web/'vocal-retrigger-data.json').write_text(raw);(root/'preparation-identity.json').write_text(json.dumps(identity,indent=2)+'\n');print('packaged',len(cases),'cases',[(c['aTitle'],c['assets']['aOneShot']['peak']) for c in cases])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['select','package']);p.add_argument('root',type=pathlib.Path);p.add_argument('--parent',type=pathlib.Path);p.add_argument('--details',type=pathlib.Path);p.add_argument('--web',type=pathlib.Path);a=p.parse_args();select(a.root,a.parent,a.details) if a.mode=='select' else package(a.root,a.web)
