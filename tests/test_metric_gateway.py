import copy,unittest
from metric_mix.prepare import validated_plan,joint_stretch
from unittest.mock import patch
import numpy as np
from types import SimpleNamespace

class CueValidationTest(unittest.TestCase):
 def tracks(self):
  bars=[{'start':i*2.,'end':i*2.+2,'beats':[i*2.+j*.5 for j in range(4)],'valid':True} for i in range(12)]
  def t(i):
   source={'reportId':str(i)*64,'masterSha256':'a'*64,'reportSha256':'b'*64,'vocalSha256':'c'*64}
   return {'id':'track-'+str(i),'title':str(i),'bpm':120,'duration':30,'reportId':source['reportId'],'provenance':{**source,'runId':'run-1'},'alignment':{'source':source,'bars':bars,'bandFrames':[{'start':j*.25,'end':(j+1)*.25,'rmsDbfs':-12,'low':-18,'mid':-18,'high':-18} for j in range(120)],'phrases':[]},'vocals':[],'windows':[],'preprocessing':{'reportId':source['reportId'],'masterSha256':'a'*64,'reportSha256':'b'*64,'bindingChecks':{'reportHash':True,'masterHash':True},'vocalActivity':{'status':'ready','unit':'ms','time_origin':'master_audio_start','source':{'track_id':'track-'+str(i),'analysis_run_id':'run-1','vocal_sha256':'c'*64},'intervals':[]}}}
  a,b=t(1),t(2);b['windows']=[{'id':'w','start':0.,'end':8.,'bars':4,'variants':{a['id']:{'duration':8.,'rate':1.}}}];return a,b
 def test_reconstructs_frozen_times_and_eq_from_trusted_window(self):
  a,b=self.tracks();p=validated_plan(a,b,'w',4.);self.assertEqual(p['duration'],8);self.assertEqual(p['end'],12);self.assertEqual(p['lastBarStart'],6);self.assertEqual(p['bassTiming'],{'duckStart':4.,'swapStart':5.5,'swapEnd':6.})
 def test_rejects_nan_and_off_grid_cues(self):
  a,b=self.tracks()
  for start in [float('nan'),4.2,-1]:
   with self.assertRaises(ValueError):validated_plan(a,b,'w',start)
 def test_local_tempo_drift_and_source_mismatch_are_not_silently_accepted(self):
  a,b=self.tracks();b['alignment']=copy.deepcopy(b['alignment']);b['alignment']['bars'][1]['beats'][2]+=.1
  with self.assertRaises(ValueError):validated_plan(a,b,'w',4.)
  a,b=self.tracks();a['alignment']['source']['masterSha256']='d'*64
  with self.assertRaises(ValueError):validated_plan(a,b,'w',4.)
class AudioCoverageTest(unittest.TestCase):
 def test_short_atempo_output_is_rejected_instead_of_zero_filled(self):
  with patch('metric_mix.prepare.read_segment',return_value=np.zeros((44100,2),dtype='float32')),patch('metric_mix.prepare.subprocess.run',return_value=SimpleNamespace(stdout=np.zeros((44090,2),dtype='<f4').tobytes())):
   with self.assertRaisesRegex(ValueError,'覆盖不足'):joint_stretch({'master':None},0,1,1.01)

if __name__=='__main__':unittest.main()

class PublicGatewayBoundaryTest(unittest.TestCase):
 def test_request_origin_and_size_are_enforced_before_any_remote_work(self):
  from fastapi.testclient import TestClient
  from metric_mix.gateway import app
  with TestClient(app) as c:
   self.assertEqual(c.post('/jobs',json={}).status_code,403)
   self.assertEqual(c.post('/jobs',content=b'x'*8193,headers={'Origin':'https://8.136.120.255'}).status_code,413)
   self.assertEqual(c.post('/jobs',json={'from':'../x','to':'b','windowId':'x','start':1},headers={'Origin':'https://8.136.120.255'}).status_code,422)
   self.assertEqual(c.get('/jobs/not-an-id').status_code,404)

class TrustedLibraryPathTest(unittest.TestCase):
 def test_versioned_catalog_details_follow_the_trusted_index(self):
  import tempfile,pathlib,json
  from metric_mix.gateway import trusted_request
  with tempfile.TemporaryDirectory() as temp:
   site=pathlib.Path(temp);release=site/'current';a,b=CueValidationTest().tracks();rows=[]
   for t in [a,b]:
    detail='catalog/import-123/details/'+t['id']+'.json';p=release/detail;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'track':t}));rows.append({'id':t['id'],'playStatus':'ready','mixStatus':'ready','detailUrl':detail})
   (release/'library.json').write_text(json.dumps({'schema':'harbeat.continuous-library.v1','tracks':rows}))
   job=trusted_request({'from':a['id'],'to':b['id'],'windowId':'w','start':4},site)
   self.assertEqual(job['a']['id'],a['id']);self.assertEqual(job['b']['id'],b['id'])
   rows[0]['detailUrl']='../private.json';(release/'library.json').write_text(json.dumps({'schema':'harbeat.continuous-library.v1','tracks':rows}))
   with self.assertRaises(ValueError):trusted_request({'from':a['id'],'to':b['id'],'windowId':'w','start':4},site)

class WorkerVersionTest(unittest.TestCase):
 def test_os_metadata_is_not_mistaken_for_executable_python(self):
  import tempfile,pathlib
  from metric_mix.prepare import worker_version
  with tempfile.TemporaryDirectory() as temp:
   root=pathlib.Path(temp);(root/'a.py').write_text('a=1');first=worker_version(root);(root/'._a.py').write_bytes(b'finder metadata');self.assertEqual(worker_version(root),first);(root/'a.py').write_text('a=2');self.assertNotEqual(worker_version(root),first)
