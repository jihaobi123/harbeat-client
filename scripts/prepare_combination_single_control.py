"""Build filter-only reference from exact previous combination assets; never re-render."""
import argparse,copy,hashlib,json,pathlib,shutil
import numpy as np
import soundfile as sf

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(work,parents,web):
 work.mkdir(parents=True,exist_ok=True);out=web/'combination-single-control-audio';out.mkdir(exist_ok=True)
 cases=[];audit=[]
 for i,parent in enumerate(parents,1):
  pack=json.loads(parent.read_text());old=pack['cases'][0];c=copy.deepcopy(old);c['id']='single-control-'+str(i).zfill(2);c['singleTechnique']='filter'
  for key,a in c['assets'].items():
   src=(web/a['url'].lstrip('/')).resolve()
   if web.resolve() not in src.parents or sha(src)!=a['sha256'] or src.stat().st_size!=a['bytes']:raise ValueError('Frozen asset changed: '+key)
   x,sr=sf.read(src,dtype='float32',always_2d=True);duration=c['pre']+c['plan']['duration'] if key.startswith('a') else c['plan']['duration'] if key.startswith('bEntry') else c['post']
   if sr!=44100 or x.shape!=(round(duration*sr),2) or not np.isfinite(x).all():raise ValueError('Frozen clock mismatch: '+key)
   dst=out/(c['id']+'-'+key+src.suffix);shutil.copy2(src,dst);a['url']='/combination-single-control-audio/'+dst.name
  if any(c[k]!=old[k] for k in ['plan','planSha256','timing','filter','vocalConflict','pre','post','bpm']):raise ValueError('Changed frozen rule')
  audit.append({'id':c['id'],'parentPackPath':str(parent.resolve()),'parentPackSha256':sha(parent),'parentSelectionSha256':pack['selectionSha256'],'parentCaseId':old['id'],'assetsByteIdentical':True,'planTimingFilterVocalConflictUnchanged':True})
  cases.append(c)
 code={str(p.relative_to(web)):sha(p) for folder in ['src/combination-step-one','src/combination-single-control'] for p in sorted((web/folder).glob('*')) if p.is_file() and not p.name.endswith('.test.ts')}
 identity={'parents':audit,'cases':cases,'sourceCodeSha256':code,'packagerSha256':sha(pathlib.Path(__file__))}
 pack={'schema':'harbeat.combination-single-control-pack.v1','selectionSha256':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),'cases':cases,'parentAudit':audit,'rendering':'Exact prior combination six assets, master/voice/EQ/cues/rate unchanged. Original and combined unchanged;single=filter-only;combined adds only unchanged bass correction. Common0.60graph/0.7output;no arm normalization.','limitation':'Two reused pairs,not new transfer evidence. Attention filter previously selected;Nevada filter-only not previously preferred. Same cached sources rehashed;no fresh NAS mutation or new source claim. Bleed/perceived loudness remain limitations. No production activation.'}
 raw=json.dumps(pack,ensure_ascii=False,indent=2)+'\n';(work/'pack.json').write_text(raw);(web/'combination-single-control-data.json').write_text(raw);(work/'preparation-identity.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2)+'\n');(work/'asset-audit.json').write_text(json.dumps(audit,indent=2)+'\n');print('Prepared',len(cases),'frozen pairs; twelve unchanged assets.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('work',type=pathlib.Path);p.add_argument('web',type=pathlib.Path);p.add_argument('parents',nargs=2,type=pathlib.Path);a=p.parse_args();prepare(a.work,a.parents,a.web)
