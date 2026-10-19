"""Source-bound finite third-track drum addition; original two-track mix is frozen."""
import argparse,copy,hashlib,json,pathlib,shutil,subprocess,math
import numpy as np
import soundfile as sf
from scripts.prepare_melody_filter import checked_asset
from scripts.prepare_vocal_endpoint_pack import validate_handover_sources
from scripts.report_vocal_endpoints import verified_analysis
SR=44100
KEYS={'aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bar_valid(b):
 return b.get('valid') and len(b.get('beats',[]))==4 and all(math.isfinite(x) for x in [b['start'],b['end'],*b['beats']]) and b['end']>b['start'] and abs(b['beats'][0]-b['start'])<=.001 and all(b['start']<=x<b['end'] and (i==0 or x>b['beats'][i-1]) for i,x in enumerate(b['beats']))
def plan_accent(c,donor,bar):
 p=c['plan'];loop=donor['loop'];source=next((b for b in loop['metrics']['earlierBars'] if b['start']==loop['sourceStart'] and b['end']==loop['sourceEnd']),None)
 if c['baselineBass']!='reference' or donor['plan']['from'] in [p['from'],p['to']] or not source or not bar_valid(source) or not bar_valid(bar) or bar['start']<p['start'] or abs(bar['end']-p['end'])>.065:raise ValueError('unsupported distinct source/target bars')
 start_frame=round((c['pre']+bar['start']-p['start'])*SR);end_frame=round((c['pre']+p['duration'])*SR);duration=(end_frame-start_frame)/SR;source_duration=source['end']-source['start'];rate=source_duration/duration
 errors=[abs((a-source['start'])/rate-(b-bar['start'])) for a,b in zip(source['beats'],bar['beats'])]
 origin=donor['plan']['start']-donor['pre']
 if not all(math.isfinite(v) for v in [duration,rate,origin,*errors]) or duration<=0 or abs(rate-1)>.06 or max(errors)>.065 or source['start']<origin or source['end']+1>donor['plan']['end']:raise ValueError('unsupported donor duration/beat mapping/lookahead')
 return dict(schema='harbeat.third-drum-window.v1',donorTrackId=donor['plan']['from'],sourceCaseId=donor['id'],sourceBar=source,targetBar=bar,sourceOrigin=origin,sourceStart=source['start'],sourceEnd=source['end'],lookaheadSeconds=1,start=start_frame/SR,finish=end_frame/SR,frames=end_frame-start_frame,duration=duration,rate=rate,mappedBeatErrors=errors,relativeGain=.25,edgeSeconds=.005,count=1)
def stretch(source,rate,frames):
 cmd=['ffmpeg','-v','error','-nostdin','-threads','1','-f','f32le','-ar',str(SR),'-ac','2','-i','pipe:0','-af','atempo='+str(rate),'-f','f32le','-acodec','pcm_f32le','pipe:1']
 return np.frombuffer(subprocess.check_output(cmd,input=source.astype('<f4').tobytes()),dtype='<f4').reshape(-1,2)[:frames].copy()
def capture_accent(pcm,sr,fx,stretch_fn=stretch):
 if sr!=SR or pcm.ndim!=2 or pcm.shape[1]!=2 or not np.isfinite(pcm).all():raise ValueError('invalid donor PCM')
 lo=round((fx['sourceStart']-fx['sourceOrigin'])*sr);hi=round((fx['sourceEnd']+fx['lookaheadSeconds']-fx['sourceOrigin'])*sr)
 if lo<0 or hi>len(pcm) or hi<=lo:raise ValueError('donor range unavailable')
 out=stretch_fn(pcm[lo:hi].copy(),fx['rate'],fx['frames'])
 if out.shape!=(fx['frames'],2) or not np.isfinite(out).all():raise ValueError('incomplete donor transform')
 n=round(fx['edgeSeconds']*sr)
 if n*2>=len(out):raise ValueError('donor too short')
 out[:n]*=np.linspace(0,1,n,dtype='float32')[:,None];out[-n:]*=np.linspace(1,0,n,dtype='float32')[:,None];return out

def validate_original(c,ref):
 if any(c.get(k)!=ref.get(k) for k in ['aTitle','bTitle','bpm','pre','post','baselineBass','plan','planSha256','sourceVerification']) or set(c['assets'])!=KEYS or any(a!=ref['assets'][k] for k,a in c['assets'].items()):raise ValueError('original schedule/assets changed')
def parents(root):
 f=json.loads((root/'frozen-input.json').read_text());packs={}
 for k,v in f['parents'].items():
  p=pathlib.Path(v['path'])
  if sha(p)!=v['sha256']:raise ValueError('frozen parent changed')
  packs[k]=json.loads(p.read_text())
 return f,packs

def read_frozen_snapshots(f):
 tracks={}
 for row in f['richSnapshots']:
  p=pathlib.Path(row['path'])
  if sha(p)!=row['sha256']:raise ValueError('rich snapshot changed')
  t=json.loads(p.read_text())['track']
  if t['id'] in tracks:raise ValueError('duplicate rich snapshot')
  tracks[t['id']]=t
 return tracks
def validate_selection(sel,expected):
 if sel!=expected:raise ValueError('selection changed from frozen source evidence')
def selection_from_frozen(root):
 f,packs=parents(root);tracks=read_frozen_snapshots(f);observed=[]
 for v in f['analysisSources']:
  folder=pathlib.Path(v['path'])
  if sha(folder/'analysis.json')!=v['sha256']:raise ValueError('frozen observations changed')
  observed.append(verified_analysis(folder))
 cases=[];used={};audit=[]
 for i,old in enumerate(packs['ab']['cases']):
  a,b=old['evidence']['analysis'],old['evidence']['control']
  if not any(a in r['contexts'] and b in r['contexts'] for r in observed):raise ValueError('unverified original observations')
  validate_handover_sources(old,a,b);t=tracks[old['plan']['from']];v=old['sourceVerification']['a']
  if any(t['provenance'][k]!=v[k] for k in ['masterSha256','vocalSha256','reportSha256','runId']):raise ValueError('target grid snapshot binding changed')
  bar=next((x for x in t['alignment']['bars'] if x.get('valid') and abs(x['end']-old['plan']['end'])<.065 and x['start']>=old['plan']['start']),None)
  donor=next(c for c in packs['donor']['cases'] if c['id']==f['donors'][i]);c={k:copy.deepcopy(old[k]) for k in ['aTitle','bTitle','pre','post','bpm','baselineBass','plan','planSha256','sourceVerification']};c['assets']={k:v for k,v in old['assets'].items() if k in KEYS}
  try:fx=plan_accent(c,donor,bar or {})
  except ValueError as e:audit.append(dict(sourceCaseId=old['id'],pair=[old['aTitle'],old['bTitle']],reason=str(e)));continue
  c.update(id=old['id'].replace('vocal-handover','third-drum'),sourceCaseId=old['id'],accent=fx,donorTitle=donor['aTitle'],donorAsset=donor['assets']['aDrum'],donorVerification=donor['sourceVerification']['a']);cases.append(c)
  for side,key in [('a','from'),('b','to')]:
   tid=old['plan'][key];tr=tracks[tid];binding=old['sourceVerification'][side]
   if any(tr['provenance'][k]!=binding[k] for k in ['masterSha256','vocalSha256','reportSha256','runId']):raise ValueError('original rich snapshot changed')
   used[tid]=dict(id=tid,title=tr['title'],reportId=tr['reportId'],binding=binding)
  dt=tracks[fx['donorTrackId']];dv=c['donorVerification']
  if any(dt['provenance'][k]!=dv[k] for k in ['masterSha256','runId']):raise ValueError('donor rich snapshot changed')
  used[dt['id']]=dict(id=dt['id'],title=dt['title'],reportId=dt['reportId'],binding=dict(dv,reportSha256=dt['provenance']['reportSha256']))
 out=dict(schema='harbeat.third-drum-selection.v1',parents=f['parents'],cases=cases,tracks=list(used.values()),audit=audit);return out
def select(root):
 out=selection_from_frozen(root);(root/'selection.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print([(c['aTitle'],c['donorTitle'],c['accent']['rate'],max(c['accent']['mappedBeatErrors'])) for c in out['cases']])

def package(root,web):
 f,packs=parents(root);sel=json.loads((root/'selection.json').read_text());proof=json.loads((root/'source-check.json').read_text())
 validate_selection(sel,selection_from_frozen(root))
 if sel['parents']!=f['parents'] or proof['selectionSha256']!=sha(root/'selection.json') or proof['tracks']!=sel['tracks']:raise ValueError('source proof mismatch')
 out=web/'third-drum-audio';out.mkdir(exist_ok=True);cases=[]
 for x in sel['cases']:
  c=copy.deepcopy(x);ref=next(o for o in packs['ab']['cases'] if o['id']==c['sourceCaseId']);validate_original(c,ref);donor=next(o for o in packs['donor']['cases'] if o['id']==c['accent']['sourceCaseId'])
  if c['accent']!=plan_accent(ref,donor,c['accent']['targetBar']) or c['donorAsset']!=donor['assets']['aDrum'] or c['donorVerification']!=donor['sourceVerification']['a']:raise ValueError('donor evidence changed')
  assets={}
  for k,a in c['assets'].items():
   duration=c['pre']+c['plan']['duration'] if k.startswith('a') else c['plan']['duration'] if k.startswith('bEntry') else c['post'];src=checked_asset(web,a,duration);dest=out/(c['id']+'-'+k+src.suffix);shutil.copy2(src,dest);assets[k]=dict(a,url='/third-drum-audio/'+dest.name)
  src=checked_asset(web,c['donorAsset'],donor['pre']+donor['plan']['duration']);pcm,sr=sf.read(src,dtype='float32',always_2d=True);shot=capture_accent(pcm,sr,c['accent']);dest=out/(c['id']+'-cDrum.wav');sf.write(dest,shot,SR,subtype='PCM_24');decoded,_=sf.read(dest,dtype='float32',always_2d=True)
  assets['cDrum']=dict(url='/third-drum-audio/'+dest.name,sha256=sha(dest),bytes=dest.stat().st_size,duration=len(decoded)/SR,frames=len(decoded),sampleRate=SR,channels=2,peak=float(np.max(np.abs(decoded))));c['assets']=assets;c['captureEvidence']=dict(inputDrumSha256=c['donorAsset']['sha256'],outputSha256=assets['cDrum']['sha256'],decodedPcmSha256=hashlib.sha256(decoded.astype('<f4').tobytes()).hexdigest(),rms=float(np.sqrt(np.mean(decoded.astype('float64')**2))),normalization='none',lookahead='one second of real following donor samples, not repeated loop');cases.append(c)
 code={p:sha(web/'src/third-drum'/p) for p in ['policy.ts','graph.ts','transport.ts','rounds.ts']};code.update({p:sha(web/p) for p in ['src/vocal-bridge/automation.ts','src/vocal-bridge/policy.ts','src/v30/eq.ts','src/realtime/cache.ts','public/low-handoff-clock.js']});identity=dict(frozenInputSha256=sha(root/'frozen-input.json'),sourceSelectionSha256=sha(root/'selection.json'),sourceCheckSha256=sha(root/'source-check.json'),packagerSha256=sha(pathlib.Path(__file__)),playbackSourceSha256=code,cases=[dict(id=c['id'],planSha256=c['planSha256'],assets=c['assets'],accent=c['accent']) for c in cases]);pack=dict(schema='harbeat.third-drum-pack.v1',selectionSha256=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),cases=cases,audit=sel['audit'],rendering='Original six5197dry clips/cues/fades/EQ, optional finite third-track drum bar at original final Abar, .25relative donor gain/.36common graph/.7output. No previous low-EQ timing/other effects inherited.',limitation='Three pairs/8tracks, Nevada donor shared first2. Additive Cdrum layer only, not full mashup/role replacement or repeated loop. Added loudness/energy and source separation bleed may influence preference. Raw measured grid, no semantic phrase certification; original cached source edges/atempo inherited.')
 raw=json.dumps(pack,ensure_ascii=False,indent=2)+'\n';(root/'pack.json').write_text(raw);(web/'third-drum-data.json').write_text(raw);(root/'preparation-identity.json').write_text(json.dumps(identity,indent=2)+'\n');print('packaged',len(cases),'cases')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['select','package']);p.add_argument('root',type=pathlib.Path);p.add_argument('--web',type=pathlib.Path);a=p.parse_args();select(a.root) if a.action=='select' else package(a.root,a.web)
