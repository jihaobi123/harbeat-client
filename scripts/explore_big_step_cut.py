from pathlib import Path
import json,argparse
p=argparse.ArgumentParser();p.add_argument("root",type=Path);p.add_argument("details",type=Path);args=p.parse_args()
T=[json.loads(p.read_text())['track'] for p in args.details.glob('*.json')]
def protected(t,s,e):return any(u-.3<e and v+.3>s for u,v in t['vocals']) or any(x['start']<e and x['tailEnd']>s for x in t['alignment']['phrases'])
A=[];B=[]
for t in T:
 if not t['bars'] or not t['alignment']['bars']:continue
 for sec in t['sections']:
  end=sec['end'];near=min((abs(x-end),x) for x in t['bars']);cut=near[1]
  if near[0]>.15 or cut<t['duration']*.5 or cut+3.2>t['duration'] or protected(t,cut-.3,cut+.08):continue
  A.append((t,sec,cut,near[0]))
 for sec in t['sections']:
  start=sec['start'];near=min((abs(x['start']-start),i) for i,x in enumerate(t['alignment']['bars']));i=near[1]
  bars=t['alignment']['bars'][i:i+2]
  if near[0]>.15 or len(bars)!=2 or not all(x['valid'] for x in bars) or abs(bars[0]['end']-bars[1]['start'])>.001:continue
  cue=bars[0]['start'];end=bars[-1]['end'];d=end-cue
  if not 2.5<d<8 or end+8>t['duration']:continue
  if any(x['start']<cue-.001 and x['tailEnd']>cue-.08 for x in t['alignment']['phrases']):continue
  B.append((t,sec,cue,end,near[0],d))
rows=[]
for a,asec,cut,ad in A:
 for b,bsec,entry,bend,bd,d in B:
  ratio=b['bpm']/a['bpm']
  if a['id']==b['id'] or min(abs(ratio-1),abs(1/ratio-1))<.18 or min(abs(ratio/2-1),abs(ratio/.5-1))<.1 or abs(a['bpm']-b['bpm'])<20:continue
  if cut+d>a['duration']-.1 or protected(a,cut-.3,cut+d+.08):continue
  rows.append(dict(a=a['title'],b=b['title'],aid=a['id'],bid=b['id'],abpm=a['bpm'],bbpm=b['bpm'],start=cut,end=cut+d,duration=d,bEntry=entry,bEnd=bend,aSection=asec,bSection=bsec,aBoundaryDistance=ad,bBoundaryDistance=bd,ratio=ratio))
rows.sort(key=lambda x:(x['aBoundaryDistance']+x['bBoundaryDistance'],abs(x['ratio']-1),x['a'],x['b'],x['start']))
o=args.root;o.mkdir(exist_ok=True);(o/'exploration.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
used=set();chosen=[]
for x in rows:
 if x['aid'] not in used and x['bid'] not in used:chosen.append(x);used.update([x['aid'],x['bid']])
 if len(chosen)==3:break
if len(chosen)!=3:raise ValueError('need3unique eligible pairs')
(o/'frozen-cues.json').write_text(json.dumps(chosen,ensure_ascii=False,indent=2)+'\n')
print(len(rows),'eligible candidates;',len(chosen),'frozen pairs')
