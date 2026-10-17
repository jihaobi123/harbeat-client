import importlib.util,pathlib,tempfile,unittest,wave
import numpy as np
spec=importlib.util.spec_from_file_location('coverage',pathlib.Path(__file__).with_name('render_bass_coverage.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TestCoverageRenderer(unittest.TestCase):
 def test_accepts_verified_common_master_rate_and_rejects_unsupported_source(self):
  m.validate_formats([{'channels':2,'sample_rate_hz':48000},{'channels':2,'sample_rate_hz':44100}])
  with self.assertRaises(ValueError):m.validate_formats([{'channels':2,'sample_rate_hz':16000},{'channels':2,'sample_rate_hz':44100}])
 def test_mixed_sample_rates_stay_on_the_same_source_time_axis(self):
  with tempfile.TemporaryDirectory() as td:
   paths=[]
   for rate,scale,name in [(48000,1,'master'),(44100,.3,'bass')]:
    t=np.arange(rate*2)/rate;x=np.column_stack([np.sin(2*np.pi*70*t)*.2,np.cos(2*np.pi*110*t)*.2])*scale;p=pathlib.Path(td)/(name+'.wav');paths.append(p)
    with wave.open(str(p),'wb') as f:f.setnchannels(2);f.setsampwidth(2);f.setframerate(rate);f.writeframes((x*32767).astype('<i2').tobytes())
   out=m.stretch_pair(paths,.2,.5,.98999375);self.assertEqual(out.shape,(22050,4));np.testing.assert_allclose(out[:,2:],out[:,:2]*.3,atol=.00015)
if __name__=='__main__':unittest.main()
