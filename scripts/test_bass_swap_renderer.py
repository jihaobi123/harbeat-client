import importlib.util,pathlib,tempfile,unittest,wave
import numpy as np
spec=importlib.util.spec_from_file_location('bass',pathlib.Path(__file__).with_name('render_bass_swap.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TestBass(unittest.TestCase):
 def test_shared_four_channel_source_alignment(self):
  with tempfile.TemporaryDirectory() as td:
   paths=[];t=np.arange(88200)/44100;x=np.column_stack([np.sin(2*np.pi*70*t)*.2,np.cos(2*np.pi*110*t)*.2])
   for name,scale in [('master',1),('bass',.3)]:
    p=pathlib.Path(td)/(name+'.wav');paths.append(p)
    with wave.open(str(p),'wb') as f:f.setnchannels(2);f.setsampwidth(2);f.setframerate(44100);f.writeframes((x*scale*32767).astype('<i2').tobytes())
   for rate in [1,.98999375]:
    out=m.stretch_pair(paths,.2,.5,rate);self.assertEqual(out.shape,(22050,4));self.assertTrue(np.isfinite(out).all());np.testing.assert_allclose(out[:,2:],out[:,:2]*.3,atol=4e-5)
 def test_rejects_invalid_range(self):
  with self.assertRaises(ValueError):m.stretch_pair([],0,float('nan'),1)
 def test_public_asset_route_and_float_preservation(self):
  with tempfile.TemporaryDirectory() as td:
   a=m.write_bass_asset(pathlib.Path(td)/'source.flac',np.full((4410,2),1.2,dtype=np.float32));self.assertTrue(a['url'].startswith('/bass-audio/'));self.assertTrue(a['url'].endswith('.wav'));self.assertEqual(a['frames'],4410)
if __name__=='__main__':unittest.main()
