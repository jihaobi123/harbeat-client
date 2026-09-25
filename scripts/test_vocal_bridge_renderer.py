import importlib.util, pathlib, tempfile, unittest, wave
import numpy as np
spec=importlib.util.spec_from_file_location('renderer',pathlib.Path(__file__).with_name('render_vocal_bridge.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class RenderTests(unittest.TestCase):
 def test_joint_stretch_preserves_channel_relationship_and_exact_length(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);sr=44100;t=np.arange(sr*4)/sr
   signal=(np.sin(t*2*np.pi*233)*.4+np.sin(t*2*np.pi*59)*.2)
   for name,scale in [('m',1),('v',.25)]:
    with wave.open(str(root/(name+'.wav')),'wb') as f:
     f.setparams((2,2,sr,0,'NONE','none'));x=np.repeat((signal*scale)[:,None],2,axis=1);f.writeframes(np.round(x*32768).astype('<i2').tobytes())
   m,v=r.stretch_pair(root/'m.wav',root/'v.wav',.2,2,1.03)
   self.assertEqual(m.shape,(sr*2,2)); self.assertEqual(v.shape,m.shape)
   self.assertLess(float(np.max(np.abs(m*.25-v))),.00003)
 def test_source_hash_failure(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'x';p.write_bytes(b'wrong')
   with self.assertRaises(ValueError):r.checked_source(pathlib.Path(d),{'storage_key':'x','sha256':'no'})
   with self.assertRaises(ValueError):r.checked_source(pathlib.Path(d),{'storage_key':'../escape','sha256':'no'})
if __name__=='__main__':unittest.main()
