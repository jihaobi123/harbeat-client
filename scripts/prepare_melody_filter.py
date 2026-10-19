"""Package identical cached excerpts; the browser applies only the stem filter."""
import argparse,hashlib,json,pathlib,copy,shutil
import numpy as np
import soundfile as sf
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate_bindings(case,row):
 if row['id']!=case['sourceCaseId'] or row['fromTrack']!=case['plan']['from'] or row['toTrack']!=case['plan']['to'] or row['bindings']!=case['sourceVerification']:raise ValueError('fresh source proof changed')
def checked_asset(web,asset,duration):
 web=web.resolve();p=(web/asset['url'].lstrip('/')).resolve()
 if web not in p.parents or not p.is_file() or sha(p)!=asset['sha256'] or p.stat().st_size!=asset['bytes']:raise ValueError('cached asset hash/bytes/path changed')
 x,sr=sf.read(p,dtype='float32',always_2d=True)
 if sr!=44100 or x.shape!=(round(duration*sr),2) or not np.isfinite(x).all():raise ValueError('cached source clock/format changed')
 return p
def package(root,parent,web):
 frozen=json.loads((root/'frozen-input.json').read_text());selection=json.loads((root/'selection.json').read_text());original=json.loads((parent/'pack.json').read_text());proof=json.loads((root/'source-check.json').read_text())
 if any(x!=sha(parent/'pack.json') for x in [frozen['sourcePackSha256'],selection['sourcePackSha256'],proof['sourcePackSha256']]) or len(selection['cases'])!=3 or len(proof['cases'])!=3:raise ValueError('frozen sourcepack/proof mismatch')
 output=web/'melody-filter-audio';output.mkdir(exist_ok=True);cases=[];audit=[];keys={'aMaster','aOther','bEntryMaster','bEntryOther','bBodyMaster','bBodyOther'}
 for c in selection['cases']:
  c=copy.deepcopy(c);old=next(x for x in original['cases'] if x['id']==c['sourceCaseId']);row=next(x for x in proof['cases'] if x['id']==c['sourceCaseId']);validate_bindings(c,row)
  if c['plan']!=old['plan'] or c['vocalConflict']!=old['vocalConflict'] or c['assets']!=old['assets'] or set(c['assets'])!=keys or c['filter']['sourceStart']!=old['lastBarSourceStart'] or any(c['filter'][k]!=v for k,v in frozen['filter'].items()):raise ValueError('original clock/rules/assets or effect changed')
  assets={}
  for key,a in c['assets'].items():
   duration=c['pre']+c['plan']['duration'] if key.startswith('a') else c['plan']['duration'] if key.startswith('bEntry') else c['post'];p=checked_asset(web,a,duration);target=output/(c['id']+'-'+key+p.suffix);shutil.copy2(p,target);assets[key]=dict(a,url='/melody-filter-audio/'+target.name)
  c['assets']=assets;c['freshSourceProof']=row;cases.append(c);audit.append(dict(id=c['id'],sourceCaseId=old['id'],exactCachedHashes={k:a['sha256'] for k,a in assets.items()},sourcePlanUnchanged=True,originalVocalConflictUnchanged=True))
 files=['policy.ts','graph.ts','transport.ts'];code={f:sha(web/'src/melody-filter'/f) for f in files};code.update({f:sha(web/f) for f in ['src/vocal-bridge/automation.ts','src/vocal-bridge/policy.ts','src/v30/eq.ts','src/melody-overlap/policy.ts']});identity=dict(frozenInputSha256=sha(root/'frozen-input.json'),selectionSha256=sha(root/'selection.json'),freshSourceProofSha256=sha(root/'source-check.json'),packagerSha256=sha(pathlib.Path(__file__)),playbackSourceSha256=code,clockWorkletSha256=sha(web/'public/vocal-echo-clock.js'),cases=[dict(id=c['id'],planSha256=c['planSha256'],assets=c['assets'],filter=c['filter']) for c in cases])
 pack=dict(schema='harbeat.melody-filter-pack.v1',selectionSha256=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),sourcePackSha256=frozen['sourcePackSha256'],cases=cases,audit=audit,rendering='Same six cached5198master/other clips and original fades/EQ/cues;only Aother final-bar highpass filtered-minus-dry correction.20->1800Hz,linearQ=1/sqrt2/WebAudioQ=-3.0103dB,20msactivation.Common0.60graphgain/0.7output and same limiter;no arm normalization.',limitation='Other is a mixed instrumental residual, with possible voice/drum/bass bleed; no pure melody claim.3pairs/5tracks, first2shareB. Inherited cached master/other atempo/source-edge rendering shared in both arms; not newly native-bitexact or source-continuity-certified. No genre trigger, combined technique or production change.')
 raw=json.dumps(pack,ensure_ascii=False,indent=2)+'\n';(root/'pack.json').write_text(raw);(web/'melody-filter-data.json').write_text(raw);(root/'asset-audit.json').write_text(json.dumps(audit,indent=2)+'\n');(root/'preparation-identity.json').write_text(json.dumps(identity,indent=2)+'\n');print('packaged',len(cases),'cases /18unchanged cached assets')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);p.add_argument('parent',type=pathlib.Path);p.add_argument('web',type=pathlib.Path);a=p.parse_args();package(a.root,a.parent,a.web)
