import argparse,json,pathlib,hashlib
read=lambda p:json.loads(p.read_text())
def prepare_input(work):
 parent=work.parent;feedback=[('neighbors',parent/'bass-neighbors-20261017/user-feedback-20261018.json'),('coverage',parent/'bass-generalization-20261017/user-feedback.json')];tracks={}
 for f in (parent/'bass-generalization-20261017/details').glob('*.json'):
  t=read(f)['track'];tracks[t['id']]=t
 cases=[];sources=[]
 for label,file in feedback:
  p=read(file);r=p['current']
  if r['practice']:raise ValueError('listener feedback required')
  sources.append({'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'roundId':r['id'],'trial':label})
  for c in p['pack']['cases']:
   f=r['cases'][c['id']];mode=f['mapping'].get(f['choice'],'reference');cases.append({**c,'baselineBass':'stem' if mode=='stem' else 'reference','previousChoice':{'roundId':r['id'],'choice':f['choice'],'method':mode,'trial':label},'originalCaseId':c['id']})
 ids={x for c in cases for x in [c['plan']['from'],c['plan']['to']]};s={'schema':'harbeat.drum-loop-candidates.v1','cases':cases,'tracks':[{'id':t['id'],'title':t['title'],'provenance':t['provenance'],'bars':[{k:b[k] for k in ['start','end','beats','valid']} for b in t['alignment']['bars']]} for id,t in tracks.items() if id in ids],'feedbackSources':sources};(work/'input.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
def pick_profiles(profiles,from_by_case):
 thinning=sorted([r for r in profiles if r['eligible'] and r['category']=='thinning'],key=lambda r:(r['metrics']['ratio'],r['caseId']))
 stable=sorted([r for r in profiles if r['eligible'] and r['category']=='stable'],key=lambda r:(abs(r['metrics']['ratio']-1),r['caseId']))
 options=[]
 for control in stable:
  used={from_by_case[control['caseId']]};chosen=[]
  for r in thinning:
   tid=from_by_case[r['caseId']]
   if tid not in used:chosen.append(r);used.add(tid)
   if len(chosen)==2:break
  if chosen:options.append(((-len(chosen),sum(r['metrics']['ratio'] for r in chosen),abs(control['metrics']['ratio']-1),control['caseId']),chosen+[control]))
 return min(options,key=lambda x:x[0])[1] if options else []
def select(work):
 data=read(work/'input.json');profiles=read(work/'profiles.json');by_id={c['id']:c for c in data['cases']};selected=[];used=set()
 for row in pick_profiles(profiles,{id:c['plan']['from'] for id,c in by_id.items()}):
  c=by_id[row['caseId']];selected.append({**c,'id':'drum-loop-'+str(len(selected)+1).zfill(2),'loop':row['loop'],'drumProfileVerification':row['sourceVerification']})
 if len(selected)<2 or not any(c['loop']['category']=='thinning' for c in selected) or not any(c['loop']['category']=='stable' for c in selected):raise ValueError('No usable thinning/control contrast; preserve profile and report rather than relabel.')
 ids={x for c in selected for x in [c['plan']['from'],c['plan']['to']]};out={'schema':'harbeat.drum-loop-selection.v1','cases':selected,'tracks':[t for t in data['tracks'] if t['id'] in ids],'audit':{'candidateCount':len(profiles),'feedbackSources':data['feedbackSources'],'requested':{'thinning':2,'stable':1},'actual':{k:sum(c['loop']['category']==k for c in selected) for k in ['thinning','stable']},'profileSha256':hashlib.sha256((work/'profiles.json').read_bytes()).hexdigest(),'profiles':profiles,'selectionRule':'fixed prior pairs only; reserve stable contrast; maximize eligible thinning slots, then strongest measured decline and stable ratio closest to1; distinct outgoing tracks; no listening-based choice','limitations':['acoustic RMS/activity proxies are not verified groove quality','ties preserve original bass treatment','target last measured bar endpoint snapped within existing65ms tolerance to exact frozen A exit']}};(work/'selection.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print([(c['aTitle'],c['bTitle'],c['loop']['category']) for c in selected])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['input','select']);p.add_argument('--work',type=pathlib.Path,required=True);a=p.parse_args();(prepare_input if a.phase=='input' else select)(a.work)
