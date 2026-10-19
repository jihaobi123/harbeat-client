"""Freeze an existing preferred bass case and add only its source-aligned Aother filter."""
import argparse,copy,hashlib,json,pathlib,shutil
import numpy as np
import soundfile as sf

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(work,base,filtered,web):
 bpack=json.loads(base.read_text());fpack=json.loads(filtered.read_text())
 b=next(c for c in bpack['cases'] if c['aTitle']=='Attention' and c['bTitle']=='HIPHOP')
 f=next(c for c in fpack['cases'] if c['aTitle']=='Attention' and c['bTitle']=='HIPHOP')
 for k in ['plan','planSha256','vocalConflict','pre','post','bpm']:
  if b[k]!=f[k]:raise ValueError('Frozen rule/clock mismatch: '+k)
 for side in ['a','b']:
  for k in ['runId','manifestSha256','masterSha256']:
   if b['sourceVerification'][side][k]!=f['sourceVerification'][side][k]:raise ValueError('Source identity mismatch')
 if b['assets']['aMaster']['sha256']!=f['assets']['aMaster']['sha256']:raise ValueError('Aother has a different parent master clip')
 work.mkdir(parents=True,exist_ok=True);out=web/'combination-step-one-audio';out.mkdir(exist_ok=True)
 c=copy.deepcopy(b);c.update(id='combination-01',filter=copy.deepcopy(f['filter']),sourceVerification={'bassParent':b['sourceVerification'],'filterAParent':f['sourceVerification']['a']},features={'bassTiming':b['timing'],'filter':f['filter'],'priorPreference':'5190 bass selected,5206 filter selected; no direct all-single ranking'})
 wanted={k:b['assets'][k] for k in ['aMaster','aBass','bEntryMaster','bEntryBass','bBodyMaster']};wanted['aOther']=f['assets']['aOther'];assets={};audit=[]
 for k,a in wanted.items():
  p=(web/a['url'].lstrip('/')).resolve()
  if web.resolve() not in p.parents or sha(p)!=a['sha256'] or p.stat().st_size!=a['bytes']:raise ValueError('Asset identity mismatch: '+k)
  x,sr=sf.read(p,dtype='float32',always_2d=True);duration=c['pre']+c['plan']['duration'] if k.startswith('a') else c['plan']['duration'] if k.startswith('bEntry') else c['post']
  if sr!=44100 or x.shape!=(round(duration*sr),2) or not np.isfinite(x).all():raise ValueError('Invalid source clock: '+k)
  target=out/(c['id']+'-'+k+p.suffix);shutil.copy2(p,target);assets[k]={**a,'url':'/combination-step-one-audio/'+target.name};audit.append({'key':k,'sha256':a['sha256'],'frames':len(x),'unchangedCachedSource':True})
 c['assets']=assets
 # Frozen parent rendering differs on B despite identical source clocks. Keep the
 # complete preferred bass reference; only Aother is borrowed, whose A master is identical.
 mismatch={}
 for k in ['aMaster','bEntryMaster','bBodyMaster']:
  x,sr=sf.read(web/b['assets'][k]['url'].lstrip('/'),dtype='float32',always_2d=True);y,_=sf.read(web/f['assets'][k]['url'].lstrip('/'),dtype='float32',always_2d=True)
  mismatch[k]={'maxDecodedDifference':float(np.max(np.abs(x-y))),'decision':'Use entire5190master/bass rendering; borrow only Aother from5206'}
 code={str(p.relative_to(web)):sha(p) for p in sorted((web/'src/combination-step-one').glob('*.ts')) if not p.name.endswith('.test.ts')}
 for n in ['src/bass-swap/policy.ts','src/melody-filter/policy.ts','src/vocal-bridge/automation.ts','src/v30/eq.ts','src/melody-overlap/policy.ts','public/vocal-echo-clock.js']:code[n]=sha(web/n)
 identity={'bassParentPackSha256':sha(base),'filterParentPackSha256':sha(filtered),'planSha256':c['planSha256'],'timing':c['timing'],'filter':c['filter'],'assets':assets,'playbackSourceSha256':code,'packagerSha256':sha(pathlib.Path(__file__))}
 pack={'schema':'harbeat.combination-step-one-pack.v1','selectionSha256':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),'cases':[c],'rendering':'Original5190master/bass source clocks, originalEQ/fades and source cuts. Single=bass handoff;combined adds only5206Aother final-bar20->1800Hz highpass. Common0.60graph/0.7output,no individual normalization.','limitation':'One reused pair; selected previously preferred single,not head-to-head best of all singles. Stem bleed and loudness remain possible confounds. Bparent cache render mismatch deliberately excluded. Cached assets rehashed; existing NAS bindings retained, fresh NAS SSH unavailable this run. No production activation.'}
 raw=json.dumps(pack,ensure_ascii=False,indent=2)+'\n';(work/'pack.json').write_text(raw);(web/'combination-step-one-data.json').write_text(raw);(work/'preparation-identity.json').write_text(json.dumps(identity,indent=2)+'\n');(work/'asset-audit.json').write_text(json.dumps({'assets':audit,'parentRenderComparison':mismatch,'sourceProof':'Existing frozen source/run/report bindings and exact cached SHA; no new NAS proof. SSH192.168.10.2 closed before authentication.'},indent=2)+'\n')
 print('Prepared one pair / six frozen assets; Aparent exact, Bparent mismatch excluded.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('work',type=pathlib.Path);p.add_argument('bass_pack',type=pathlib.Path);p.add_argument('filter_pack',type=pathlib.Path);p.add_argument('web',type=pathlib.Path);a=p.parse_args();prepare(a.work,a.bass_pack,a.filter_pack,a.web)
