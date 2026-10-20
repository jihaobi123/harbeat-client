"""Replicate one fixed bass+other-filter method on frozen bass-preferred pairs."""
import argparse,copy,hashlib,json,math,pathlib,shutil
import numpy as np
import soundfile as sf
from render_melody_overlap import sha,stretch_layers,write_asset

def make_filter(c,t):
 p=c['plan'];v=c['sourceVerification']['a'];pro=t['provenance'];a=t['alignment'];s=a['source'];start=p['start']+c['timing']['swapEnd']
 if t['id']!=p['from'] or pro['runId']!=v['runId'] or pro['masterSha256']!=v['masterSha256'] or any(pro[k]!=s[k] for k in ['masterSha256','reportSha256','vocalSha256']):raise ValueError('Unbound A grid/source')
 bars=[b for b in a['bars'] if abs(b['start']-start)<.001]
 if len(bars)!=1:raise ValueError('Original last bar changed')
 b=bars[0];beats=b['beats']
 if not b['valid'] or len(beats)!=4 or abs(b['end']-p['end'])>.065 or abs(beats[0]-b['start'])>.001 or any(not math.isfinite(x) or x<b['start'] or x>=b['end'] or i and x<=beats[i-1] for i,x in enumerate(beats)):raise ValueError('Incomplete observed final bar')
 return dict(type='highpass',startHz=20,endHz=1800,Q=math.sqrt(.5),edgeSeconds=.02,sourceStart=b['start'],sourceBar=copy.deepcopy(b),gridSource=copy.deepcopy(s),endOffsetFromObservedBar=p['end']-b['end'])

def eligible_alignment(comparisons):
 return set(comparisons)=={'aMaster','aBass'} and all(math.isfinite(x) and 0<=x<=2e-7 for x in comparisons.values())

def read_frozen(work):
 f=json.loads((work/'frozen-input.json').read_text())
 if len(f['cases'])!=3:raise ValueError('Expected3preselected pairs')
 for row in f['cases']:make_filter(row['case'],row['sourceTrack'])
 return f

def remote_sources(work,nas,reports):
 f=read_frozen(work);out=work/'source-audio';out.mkdir(exist_ok=True);checked={};proof=[]
 for index,row in enumerate(f['cases']):
  c=row['case'];paths={};bindings={}
  for side,field in [('a','from'),('b','to')]:
   tid=c['plan'][field];v=c['sourceVerification'][side];m=nas/'published/tracks'/tid/'runs'/v['runId']/'manifest.json';doc=json.loads(m.read_text());done=json.loads((m.parent/'_SUCCESS.json').read_text());eqsource=c['plan']['v30Eq']['sources'][side]
   if sha(m)!=v['manifestSha256'] or sha(m)!=done['manifest_sha256'] or doc['track_id']!=tid or doc['analysis_run_id']!=v['runId']:raise ValueError('NAS manifest identity changed')
   report=reports/(eqsource['reportId']+'.json')
   if sha(report)!=eqsource['reportSha256'] or eqsource['masterSha256']!=v['masterSha256']:raise ValueError('Bound report changed')
   checked_paths={};assets={}
   for name in ['master','bass','vocals']+(['other'] if side=='a' else []):
    asset=doc['assets']['master'] if name=='master' else doc['assets']['stems'][name];p=(nas/asset['storage_key']).resolve()
    expected=v['masterSha256'] if name=='master' else v['bassSha256'] if name=='bass' else eqsource['vocalSha256'] if name=='vocals' else asset['sha256']
    if nas.resolve() not in p.parents or asset['sha256']!=expected or sha(p)!=expected or asset['channels']!=2 or asset['sample_rate_hz'] not in ((44100,48000) if name=='master' else (44100,)):raise ValueError('Actual NAS source identity/format changed')
    checked_paths[name]=p;assets[name]=asset
   if side=='a':
    source=row['sourceTrack']['alignment']['source']
    if source!=eqsource:raise ValueError('Grid and EQ reports disagree')
   paths[side]=checked_paths;bindings[side]={'trackId':tid,'runId':v['runId'],'manifestSha256':sha(m),'report':eqsource,'assets':assets};checked[tid]=bindings[side];print('verified',tid,flush=True)
  p=c['plan'];pcm=stretch_layers([paths['a']['master'],paths['a']['bass'],paths['a']['other']],p['start']-c['pre'],c['pre']+p['duration'],1)
  probes={k:write_asset(out/(f'neighbor-{index+1:02d}-'+k+'.flac'),pcm[:,i*2:i*2+2]) for i,k in enumerate(['aProbeMaster','aProbeBass','aOther'])}
  proof.append({'parentCaseId':c['id'],'bindings':bindings,'filter':make_filter(c,row['sourceTrack']),'probes':probes});print('rendered-A',c['id'],flush=True)
 (work/'source-check.json').write_text(json.dumps({'schema':'harbeat.combination-neighbor-source-check.v1','frozenInputSha256':sha(work/'frozen-input.json'),'sourceTracks':len(checked),'cases':proof},ensure_ascii=False,indent=2)+'\n')

def checked_asset(web,a,duration):
 p=(web/a['url'].lstrip('/')).resolve()
 if web.resolve() not in p.parents or not p.is_file() or sha(p)!=a['sha256'] or p.stat().st_size!=a['bytes']:raise ValueError('Cached asset mismatch')
 x,sr=sf.read(p,dtype='float32',always_2d=True)
 if sr!=44100 or x.shape!=(round(duration*sr),2) or not np.isfinite(x).all():raise ValueError('Cached clock mismatch')
 return p,x

def package(work,web):
 f=read_frozen(work);proof=json.loads((work/'source-check.json').read_text())
 if proof['frozenInputSha256']!=sha(work/'frozen-input.json') or len(proof['cases'])!=3 or proof['sourceTracks']!=6:raise ValueError('Fresh source proof differs')
 out=web/'combination-neighbors-audio';out.mkdir(exist_ok=True);cases=[];audit=[]
 for i,(row,pr) in enumerate(zip(f['cases'],proof['cases'])):
  path=pathlib.Path(row['parentPath']);detail=pathlib.Path(row['sourceDetailPath'])
  if sha(path)!=row['parentPackSha256'] or sha(detail)!=row['sourceDetailSha256'] or json.loads(detail.read_text())['track']!=row['sourceTrack']:raise ValueError('Frozen parent/detail changed')
  c=copy.deepcopy(row['case']);old=next(x for x in json.loads(path.read_text())['cases'] if x['id']==c['id'])
  if c!=old or pr['parentCaseId']!=c['id'] or pr['filter']!=make_filter(c,row['sourceTrack']):raise ValueError('Parent case or observed filter changed')
  cid=f'combination-neighbor-{i+1:02d}';assets={};decoded={}
  for key in ['aMaster','aBass','bEntryMaster','bEntryBass','bBodyMaster']:
   duration=c['pre']+c['plan']['duration'] if key.startswith('a') else c['plan']['duration'] if key.startswith('bEntry') else c['post'];p,x=checked_asset(web,c['assets'][key],duration);target=out/(cid+'-'+key+p.suffix);assets[key]={**c['assets'][key],'url':'/combination-neighbors-audio/'+target.name};decoded[key]=x
  comparisons={}
  for probe,key in [('aProbeMaster','aMaster'),('aProbeBass','aBass'),('aOther','aOther')]:
   a=pr['probes'][probe];p=work/'source-audio'/pathlib.Path(a['url']).name
   if sha(p)!=a['sha256'] or p.stat().st_size!=a['bytes']:raise ValueError('Fresh Aprobe changed')
   x,sr=sf.read(p,dtype='float32',always_2d=True)
   if sr!=44100 or x.shape!=decoded['aMaster'].shape or not np.isfinite(x).all():raise ValueError('Fresh Aprobe clock mismatch')
   if key!='aOther':
    comparisons[key]=float(np.max(np.abs(x-decoded[key])))
   else:
    target=out/(cid+'-aOther'+p.suffix);assets[key]={**a,'url':'/combination-neighbors-audio/'+target.name};rms=float(np.sqrt(np.mean(x.astype('float64')**2)))
    if rms<.005:raise ValueError('Aother too quiet for meaningful filter audition')
  row_audit={'id':cid,'parentCaseId':c['id'],'parentPackSha256':row['parentPackSha256'],'aProbeDecodedDifference':comparisons,'otherRms':rms,'eligible':eligible_alignment(comparisons)}
  if not row_audit['eligible']:
   row_audit['reason']='New6channel-atempo1Aprobe differs from frozen4channel parent; not a valid one-variable cached-reference comparison. Skip, not a listening failure.';audit.append(row_audit);continue
  row_audit['originalPlanVoiceTimingAssetsUnchanged']=True;audit.append(row_audit)
  for key in ['aMaster','aBass','bEntryMaster','bEntryBass','bBodyMaster']:
   source=(web/c['assets'][key]['url'].lstrip('/'));shutil.copy2(source,out/pathlib.Path(assets[key]['url']).name)
  source=work/'source-audio'/pathlib.Path(pr['probes']['aOther']['url']).name;shutil.copy2(source,out/pathlib.Path(assets['aOther']['url']).name)
  c.update(id=cid,parentCaseId=c['id'],filter=pr['filter'],assets=assets,sourceVerification=pr['bindings'],features={'priorBassPreferred':True,'newFilterPreference':None});cases.append(c)
 if not cases:raise ValueError('No source-aligned candidates remain; preserve original references')
 allowed={pathlib.Path(a['url']).name for c in cases for a in c['assets'].values()};quarantine=work/'excluded-pack-cache';quarantine.mkdir(exist_ok=True)
 for p in out.iterdir():
  if p.is_file() and p.name not in allowed:shutil.move(str(p),str(quarantine/p.name))
 code={str(p.relative_to(web)):sha(p) for folder in ['combination-step-one','combination-neighbors'] for p in sorted((web/'src'/folder).glob('*')) if p.suffix in ['.ts','.tsx','.css'] and '.test.' not in p.name}
 for n in ['src/bass-swap/policy.ts','src/melody-filter/policy.ts','src/vocal-bridge/automation.ts','src/v30/eq.ts','src/melody-overlap/policy.ts','public/vocal-echo-clock.js']:code[n]=sha(web/n)
 identity={'frozenInputSha256':sha(work/'frozen-input.json'),'freshSourceProofSha256':sha(work/'source-check.json'),'packagerSha256':sha(pathlib.Path(__file__)),'playbackSourceSha256':code,'cases':[{'id':c['id'],'planSha256':c['planSha256'],'timing':c['timing'],'filter':c['filter'],'assets':c['assets']} for c in cases]}
 pack={'schema':'harbeat.combination-neighbors-pack.v1','selectionSha256':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),'cases':cases,'candidateAudit':audit,'rendering':'Whole prior master/bass cache retained;only newly source-aligned Aother added. Same original EQ/voice/cues;single=bass,combined=bass+fixed finalbar20->1800HzHP;common0.60graph/0.7output/no arm normalization.','limitation':'Three predeclared bass-preferred candidates; only source-aligned eligible cases included. One listener; filter not previously preferred on new pairs. Conditional replication,not universal rule. Stem bleed,loudness and inherited source joins remain limits.'}
 raw=json.dumps(pack,ensure_ascii=False,indent=2)+'\n';(work/'pack.json').write_text(raw);(web/'combination-neighbors-data.json').write_text(raw);(work/'preparation-identity.json').write_text(json.dumps(identity,indent=2)+'\n');(work/'asset-audit.json').write_text(json.dumps(audit,indent=2)+'\n');print('packaged',len(cases),'eligible cases /',6*len(cases),'assets;',3-len(cases),'source-alignment skips')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['remote','package']);p.add_argument('work',type=pathlib.Path);p.add_argument('--web',type=pathlib.Path);p.add_argument('--nas',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/preprocess'));p.add_argument('--reports',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/data/analysis-platform/reports'));a=p.parse_args();remote_sources(a.work,a.nas,a.reports) if a.mode=='remote' else package(a.work,a.web)
