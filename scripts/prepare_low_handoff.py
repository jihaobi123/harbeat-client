"""Freeze measured bar timing variants; copy six identical source-bound clips."""
import argparse,copy,hashlib,json,pathlib,shutil,math
from scripts.prepare_melody_filter import checked_asset
from scripts.prepare_vocal_endpoint_pack import validate_handover_sources
from scripts.report_vocal_endpoints import verified_analysis

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def select_handoff(c):
 p=c['plan'];bars=c['evidence']['analysis']['bars'];beat=60/c['bpm'][0]
 if c['baselineBass']!='reference' or not all(math.isfinite(v) for v in [c['pre'],c['post'],*c['bpm'],p['start'],p['end'],p['duration'],p['rate'],p['window']['start'],p['window']['end']]) or c['pre']<0 or c['post']<=0 or p['rate']<=0 or abs(p['rate']-1)>.05 or abs(p['end']-p['start']-p['duration'])>.002 or abs((p['window']['end']-p['window']['start'])/p['rate']-p['duration'])>.002:raise ValueError('changed original source clock')
 if not all(math.isfinite(v) and (i==0 or v>bars[i-1]) for i,v in enumerate(bars)):raise ValueError('invalid measured bars')
 anchors=[v for i,v in enumerate(bars[:-1]) if v>=p['start'] and bars[i+1]<=p['end']+.065 and bars[i+1]-v>=beat]
 if len(anchors)<2 or anchors[-1]-anchors[0]<beat or abs(bars[bars.index(anchors[-1])+1]-p['end'])>.065 or anchors[-1]+beat>p['end']:raise ValueError('missing two complete fixed bar anchors')
 return dict(frequency=140,maxCutDb=18,rampBeats=1,earlySource=anchors[0],lateSource=anchors[-1],bars=bars)
def select(root,details):
 f=json.loads((root/'frozen-input.json').read_text());parent=pathlib.Path(f['sourcePackPath'])
 if sha(parent)!=f['sourcePackSha256']:raise ValueError('parent changed')
 original=json.loads(parent.read_text());observed=[]
 for v in f['analysisSources']:
  folder=pathlib.Path(v['path'])
  if sha(folder/'analysis.json')!=v['sha256']:raise ValueError('frozen observations changed')
  observed.append(verified_analysis(folder))
 tracks={json.loads(p.read_text())['track']['id']:json.loads(p.read_text())['track'] for p in details.glob('*.json')};cases=[];audit=[];used={}
 for old in original['cases']:
  a,b=old['evidence']['analysis'],old['evidence']['control']
  if not any(a in r['contexts'] and b in r['contexts'] for r in observed):raise ValueError('unverified frozen observations')
  validate_handover_sources(old,a,b)
  try:h=select_handoff(old)
  except ValueError as e:audit.append(dict(pair=[old['aTitle'],old['bTitle']],reason=str(e)));continue
  c={k:copy.deepcopy(old[k]) for k in ['aTitle','bTitle','bpm','pre','post','plan','planSha256','sourceVerification','baselineBass']};c.update(id=old['id'].replace('vocal-handover','low-handoff'),sourceCaseId=old['id'],handoff=h,assets={k:v for k,v in old['assets'].items() if k in ['aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal']});cases.append(c)
  for side,key in [('a','from'),('b','to')]:
   t=tracks[c['plan'][key]];v=c['sourceVerification'][side]
   if any(t['provenance'][k]!=v[k] for k in ['masterSha256','vocalSha256','reportSha256','runId']):raise ValueError('snapshot binding changed')
   used[t['id']]=dict(id=t['id'],title=t['title'],reportId=t['reportId'],binding=v)
 out=dict(schema='harbeat.low-handoff-selection.v1',sourcePackSha256=f['sourcePackSha256'],cases=cases,tracks=list(used.values()),audit=audit);(root/'selection.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print('selected',[(c['aTitle'],c['handoff']['earlySource'],c['handoff']['lateSource']) for c in cases])
def validate_frozen(c,ref):
 if any(c.get(k)!=ref.get(k) for k in ['aTitle','bTitle','bpm','pre','post','plan','planSha256','sourceVerification','baselineBass']) or c['handoff']!=select_handoff(ref) or set(c['assets'])!={'aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal'} or any(a!=ref['assets'][key] for key,a in c['assets'].items()):raise ValueError('frozen schedule/evidence/assets changed')
def package(root,web):
 f=json.loads((root/'frozen-input.json').read_text());parent=pathlib.Path(f['sourcePackPath']);sel=json.loads((root/'selection.json').read_text());proof=json.loads((root/'source-check.json').read_text())
 if sha(parent)!=f['sourcePackSha256'] or sel['sourcePackSha256']!=sha(parent) or proof['selectionSha256']!=sha(root/'selection.json') or proof['tracks']!=sel['tracks']:raise ValueError('source proof mismatch')
 old=json.loads(parent.read_text());out=web/'low-handoff-audio';out.mkdir(exist_ok=True);cases=[]
 for x in sel['cases']:
  c=copy.deepcopy(x);p=c['plan'];ref=next(o for o in old['cases'] if o['id']==c['sourceCaseId'])
  validate_frozen(c,ref)
  assets={}
  for key,a in c['assets'].items():
   if a!=ref['assets'][key]:raise ValueError('frozen source clip changed')
   duration=c['pre']+p['duration'] if key.startswith('a') else p['duration'] if key.startswith('bEntry') else c['post'];src=checked_asset(web,a,duration);target=out/(c['id']+'-'+key+src.suffix);shutil.copy2(src,target);assets[key]=dict(a,url='/low-handoff-audio/'+target.name)
  c['assets']=assets;cases.append(c)
 files=['policy.ts','graph.ts','transport.ts','rounds.ts'];code={f:sha(web/'src/low-handoff'/f) for f in files};code.update({f:sha(web/f) for f in ['src/vocal-bridge/automation.ts','src/vocal-bridge/policy.ts','src/v30/eq.ts','src/realtime/cache.ts','public/low-handoff-clock.js']});identity=dict(frozenInputSha256=sha(root/'frozen-input.json'),sourceSelectionSha256=sha(root/'selection.json'),freshSourceProofSha256=sha(root/'source-check.json'),packagerSha256=sha(pathlib.Path(__file__)),playbackSourceSha256=code,cases=[dict(id=c['id'],planSha256=c['planSha256'],assets=c['assets'],handoff=c['handoff']) for c in cases]);pack=dict(schema='harbeat.low-handoff-pack.v1',selectionSha256=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),sourcePackSha256=sha(parent),cases=cases,audit=sel['audit'],rendering='Identical six5197master/vocal clips, original clocks/fades/EQ; both arms140Hz18dB instrumental residual low shelf exchange, one estimated Abeat ramp. Only handoff anchor differs. F(M)+V-F(V) preserves original vocal transfer. Common0.36graph/0.7output/limiter.',limitation='Both arms use low-frequency processing; no untreated reference and no overall benefit claim. Low shelf affects residual kick/percussion and bleed, not isolated bass. Raw measured bars, not semantic phrases. Three fixed pairs; inherited cached source-edge/atempo behavior, no native bit-exact continuity claim.')
 raw=json.dumps(pack,ensure_ascii=False,indent=2)+'\n';(root/'pack.json').write_text(raw);(web/'low-handoff-data.json').write_text(raw);(root/'preparation-identity.json').write_text(json.dumps(identity,indent=2)+'\n');print('packaged',len(cases),'cases /18same cached assets')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['select','package']);p.add_argument('root',type=pathlib.Path);p.add_argument('--web',type=pathlib.Path);p.add_argument('--details',type=pathlib.Path);a=p.parse_args();select(a.root,a.details) if a.action=='select' else package(a.root,a.web)
