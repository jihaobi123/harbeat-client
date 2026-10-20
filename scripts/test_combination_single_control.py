import copy,hashlib,json,pathlib,tempfile,unittest
import numpy as np
import soundfile as sf
from scripts.prepare_combination_single_control import prepare

class FrozenControlTest(unittest.TestCase):
 def fixture(self,root):
  web=root/'web';web.mkdir();(web/'src/combination-step-one').mkdir(parents=True);(web/'src/combination-single-control').mkdir()
  assets={}
  for key,n in [('aMaster',88200),('aBass',88200),('aOther',88200),('bEntryMaster',44100),('bEntryBass',44100),('bBodyMaster',44100)]:
   path=web/(key+'.wav');sf.write(path,np.zeros((n,2)),44100,subtype='FLOAT');assets[key]={'url':'/'+path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
  case={'id':'old','aTitle':'a','bTitle':'b','pre':1,'post':1,'plan':{'duration':1},'planSha256':'frozen','timing':{'swapEnd':1},'filter':{'sourceStart':1},'vocalConflict':{'accepted':True},'bpm':[100,100],'assets':assets}
  parents=[]
  for i in range(2):
   p=root/('parent'+str(i)+'.json');p.write_text(json.dumps({'cases':[case],'selectionSha256':'old'}));parents.append(p)
  return web,parents,case
 def test_preserves_cached_files_and_rules_while_explicitly_selecting_filter(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);web,parents,old=self.fixture(root);prepare(root/'out',parents,web);pack=json.loads((root/'out/pack.json').read_text())
   self.assertEqual(len(pack['cases']),2)
   for c in pack['cases']:
    self.assertEqual(c['singleTechnique'],'filter')
    for key in ['plan','planSha256','timing','filter','vocalConflict','pre','post','bpm']:self.assertEqual(c[key],old[key])
    for key,a in c['assets'].items():self.assertEqual(hashlib.sha256((web/a['url'].lstrip('/')).read_bytes()).hexdigest(),old['assets'][key]['sha256'])
 def test_corrupted_source_rejected_before_copy(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);web,parents,_=self.fixture(root);(web/'aBass.wav').write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'Frozen asset changed'):prepare(root/'out',parents,web)
if __name__=='__main__':unittest.main()
