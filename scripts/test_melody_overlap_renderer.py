import importlib.util,pathlib,tempfile,unittest,wave
import numpy as np
spec=importlib.util.spec_from_file_location('melody',pathlib.Path(__file__).with_name('render_melody_overlap.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RendererTest(unittest.TestCase):
 def test_shared_six_channel_timing_and_reconstruction(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);paths=[];t=np.arange(44100*2)/44100
   stereo=np.column_stack([np.sin(2*np.pi*330*t)*.2,np.cos(2*np.pi*220*t)*.2])
   for name,scale in [('master',1),('vocal',.25),('drum',.5)]:
    p=root/(name+'.wav');paths.append(p)
    with wave.open(str(p),'wb') as f:f.setnchannels(2);f.setsampwidth(2);f.setframerate(44100);f.writeframes((stereo*scale*32767).astype('<i2').tobytes())
   for rate in [1,1.01]:
    out=m.stretch_layers(paths,.2,.5,rate)
    self.assertEqual(out.shape,(22050,6));self.assertTrue(np.isfinite(out).all())
    np.testing.assert_allclose(out[:,2:4],out[:,:2]*.25,atol=4e-5)
    np.testing.assert_allclose(out[:,4:6],out[:,:2]*.5,atol=4e-5)
    h=out[:,:2]-out[:,2:4]-out[:,4:6]
    np.testing.assert_allclose(h+out[:,2:4]+out[:,4:6],out[:,:2],atol=1e-7)
 def test_hash_and_path_rejection(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'source').write_bytes(b'abc')
   with self.assertRaises(ValueError):m.checked_source(root,{'storage_key':'source','sha256':'bad'})
   with self.assertRaises(ValueError):m.checked_source(root,{'storage_key':'../outside','sha256':'bad'})
 def test_flac_length_and_metadata(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'clip.flac';x=np.zeros((4410,2),dtype=np.float32)
   a=m.write_asset(p,x);self.assertEqual(a['frames'],4410);self.assertEqual(a['duration'],.1);self.assertEqual(a['sha256'],m.sha(p))
 def test_source_peak_above_unity_is_preserved_as_float(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'peak.flac';x=np.full((4410,2),1.2,dtype=np.float32)
   a=m.write_asset(p,x);self.assertTrue(a['url'].endswith('.wav'));self.assertGreater(a['peak'],1)
 def test_nonfinite_audio_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(ValueError):m.write_asset(pathlib.Path(td)/'bad.flac',np.full((10,2),np.nan))
if __name__=='__main__':unittest.main()
