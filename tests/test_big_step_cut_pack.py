import copy
import pytest
from scripts.package_big_step_cut import verify_frozen

def example():
 c={'id':'cut1','plan':{'start':10,'end':14,'duration':4,'rate':1,'window':{'start':20,'end':24}},'planSha256':'frozen','boundary':{'aDownbeat':10,'bDownbeat':20},'pre':4,'post':8,'cutEdgeSeconds':.005,'bpm':[98,136]}
 return c,dict(copy.deepcopy(c),assets={'aMaster':{}},sourceVerification={'a':{}},nativeContinuityAudit={})

def test_render_cannot_move_source_cues_or_cut_boundaries():
 a,b=example();verify_frozen(a,b)
 for key,value in [('pre',3),('cutEdgeSeconds',.008),('boundary',{'aDownbeat':11}),('plan',dict(a['plan'],rate=1.02)),('id','cut2')]:
  changed=dict(b,**{key:value})
  with pytest.raises(ValueError):verify_frozen(a,changed)

def test_render_cannot_add_an_undisclosed_effect_or_remove_metadata():
 a,b=example()
 with pytest.raises(ValueError):verify_frozen(a,dict(b,echo=.3))
 b.pop('bpm')
 with pytest.raises(ValueError):verify_frozen(a,b)

@pytest.fixture
def pack_fixture(tmp_path):
 import json,hashlib,pathlib
 import numpy as np
 import soundfile as sf
 from scripts.package_big_step_cut import sha
 root=tmp_path/'root';root.mkdir();audio=root/'source-audio';audio.mkdir();web=tmp_path/'web';web.mkdir()
 assets={}
 for seconds in [4,8]:
  p=audio/(str(seconds)+'.wav');sf.write(p,np.zeros((44100*seconds,2),dtype='float32'),44100,subtype='FLOAT');assets[seconds]={'url':'/native/'+p.name,'sha256':sha(p),'bytes':p.stat().st_size,'duration':seconds,'frames':44100*seconds,'channels':2,'sampleRate':44100}
 renderer=pathlib.Path(__file__).resolve().parents[1]/'scripts/render_half_double_sources.py';frozen=[];rendered=[];tracks=[]
 for i in range(3):
  c={'id':'cut'+str(i),'plan':{'from':'a'+str(i),'to':'b'+str(i),'start':10,'end':14,'duration':4,'rate':1,'window':{'start':20,'end':24}},'pre':4,'post':8,'sourceVerification':{}}
  f=copy.deepcopy(c);frozen.append(f)
  for side in ['a','b']:
   tid=side+str(i);v={'runId':tid,'reportSha256':'r','masterSha256':'m','vocalSha256':'v','manifestSha256':'s'};c['sourceVerification'][side]=v;tracks.append({'id':tid,'provenance':v,'preprocessing':{'vocalActivity':{'source':{'manifest_sha256':'s'}}}})
  c['assets']={key:copy.deepcopy(assets[4 if key.startswith('bEntry') else 8]) for key in ['aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal']};c['nativeContinuityAudit']={'directNativeNoAtempo':True,'absoluteSourceClock':True,'rendererSha256':sha(renderer),'adjacentCombinedSourceMaxError':0,'joinedPcmSha256':'e','continuousSourcePcmSha256':'e'};rendered.append(c)
 bound=[{k:v for k,v in c.items() if k not in ['assets','nativeContinuityAudit']} for c in rendered]
 def write(name,x):(root/name).write_text(json.dumps(x))
 write('selection.json',{'cases':frozen,'audit':{}});write('selection-bound.json',{'cases':bound});write('tracks.json',tracks);write('source-audio/half-double-native.json',{'selectionSha256':sha(root/'selection-bound.json'),'cases':rendered})
 return root,web

@pytest.mark.parametrize('fault',['manifest','renderer','wav','duplicate','missing'])
def test_pack_rejects_tampered_binding_format_and_cohort(pack_fixture,fault):
 import json
 from scripts.package_big_step_cut import package
 root,web=pack_fixture
 if fault=='manifest':
  p=root/'tracks.json';x=json.loads(p.read_text());x[0]['preprocessing']['vocalActivity']['source']['manifest_sha256']='wrong';p.write_text(json.dumps(x))
 elif fault=='wav':
  p=root/'source-audio/4.wav';p.write_bytes(p.read_bytes()+b'changed')
 elif fault=='duplicate':
  for name in ['selection.json','selection-bound.json','source-audio/half-double-native.json']:
   p=root/name;x=json.loads(p.read_text());x['cases'][1]['plan']['from']='a0'
   if name!='selection.json':x['cases'][1]['sourceVerification']['a']=copy.deepcopy(x['cases'][0]['sourceVerification']['a'])
   p.write_text(json.dumps(x))
  from scripts.package_big_step_cut import sha
  p=root/'source-audio/half-double-native.json';x=json.loads(p.read_text());x['selectionSha256']=sha(root/'selection-bound.json');p.write_text(json.dumps(x))
 else:
  p=root/'source-audio/half-double-native.json';x=json.loads(p.read_text())
  if fault=='renderer':x['cases'][0]['nativeContinuityAudit']['rendererSha256']='wrong'
  else:x['cases'][0]['assets'].pop('aVocal')
  p.write_text(json.dumps(x))
 with pytest.raises(ValueError):package(root,web)

def test_bound_native_pack_can_be_packaged_without_new_audio_processing(pack_fixture):
 import json
 from scripts.package_big_step_cut import package
 root,web=pack_fixture;package(root,web);p=json.loads((root/'pack.json').read_text());assert len(p['cases'])==3;assert all(len(c['assets'])==6 for c in p['cases'])
