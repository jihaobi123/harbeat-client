import hashlib,json,pathlib,tempfile,unittest
from scripts.report_vocal_endpoints import build

class ProvenanceTests(unittest.TestCase):
 def setup_files(self,r):
  audio=r/'t.wav';audio.write_bytes(b'fixed-context');h=hashlib.sha256(audio.read_bytes()).hexdigest()
  c=dict(id='t',title='test',start=0,end=5,contextSha256=h,cueStart=1,cueEnd=4,bars=[0,2,4],bpm=120,vad=[[1,2]])
  binding={k:c[k] for k in ['id','start','end','contextSha256']};(r/'contexts.json').write_text(json.dumps([c]));m=r/'t-model.json';m.write_text(json.dumps(dict(context=binding)))
  frames=[dict(t=i*.05,rms=.2 if 1<=i*.05<2 else .00001,voiced=0,voice=.95) for i in range(101)]
  (r/'t-frames.json').write_text(json.dumps(dict(context=binding,modelOutputSha256=hashlib.sha256(m.read_bytes()).hexdigest(),frames=frames)))
  return c
 def test_stale_context_output_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   r=pathlib.Path(d);c=self.setup_files(r);(r/'t.wav').write_bytes(b'new-context');c['contextSha256']=hashlib.sha256((r/'t.wav').read_bytes()).hexdigest();(r/'contexts.json').write_text(json.dumps([c]))
   with self.assertRaisesRegex(ValueError,'stale derived'):build(r)
 def test_changed_model_output_requires_pitch_regeneration(self):
  with tempfile.TemporaryDirectory() as d:
   r=pathlib.Path(d);self.setup_files(r);m=r/'t-model.json';m.write_text(m.read_text()+' ')
   with self.assertRaisesRegex(ValueError,'stale derived'):build(r)
 def test_bound_pipeline_reports_valid_candidate(self):
  with tempfile.TemporaryDirectory() as d:
   r=pathlib.Path(d);self.setup_files(r);self.assertIsNotNone(build(r)['contexts'][0]['selected'])
if __name__=='__main__':unittest.main()
