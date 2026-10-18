import unittest,numpy as np
from drum_loop_audio import classify_profile,choose_source_bar,build_loop_drums,stretch_bar
class TestDrumLoopAudio(unittest.TestCase):
 def test_energy_drop_is_a_hypothesis_not_a_stable_control(self):
  self.assertEqual(classify_profile(.2,.08,1,1,.2),'thinning')
  self.assertEqual(classify_profile(.2,.2,1,1,.2),'stable')
  self.assertIsNone(classify_profile(.2,.15,1,1,.9))
 def test_source_bar_must_precede_target_and_have_four_active_beats(self):
  bars=[{'start':0,'end':4,'beats':[0,1,2,3],'valid':True},{'start':4,'end':8,'beats':[4,5,6,7],'valid':True}]
  evidence=[{'rms':.1,'beatRms':[.1,.1,.1,.1]},{'rms':.2,'beatRms':[.2,.2,.2,.2]}]
  self.assertEqual(choose_source_bar(bars,evidence,4,.01)['index'],0)
  self.assertIsNone(choose_source_bar(bars,[{'rms':.1,'beatRms':[.1,0,.1,.1]},evidence[1]],4,.01))
 def test_replacement_uses_same_source_for_both_target_bars_and_preserves_other_samples(self):
  natural=np.column_stack([np.arange(1000),-np.arange(1000)]).astype(np.float32);seen=[]
  def stretch(source,frames):seen.append(source.copy());return np.tile(source[:1],(frames,1))
  out=build_loop_drums(natural,(100,200),[(400,600),(600,800)],stretch,fade_frames=10,seam_frames=4)
  self.assertEqual(out.shape,natural.shape);np.testing.assert_array_equal(out[:400],natural[:400]);np.testing.assert_array_equal(out[800:],natural[800:]);self.assertEqual(len(seen),2);np.testing.assert_array_equal(seen[0],seen[1]);np.testing.assert_array_equal(seen[0],natural[100:200])
 def test_invalid_loop_ranges_do_not_silently_move_source_or_endpoints(self):
  x=np.zeros((100,2),np.float32)
  with self.assertRaises(ValueError):build_loop_drums(x,(50,70),[(40,60),(60,80)],lambda s,n:np.zeros((n,2)),2,2)
class TestStretch(unittest.TestCase):
 def test_stretch_preserves_duration_and_tonal_frequency(self):
  sr=44100;t=np.arange(sr*2)/sr;x=np.column_stack([np.sin(2*np.pi*220*t),np.sin(2*np.pi*440*t)]).astype(np.float32)*.1;n=round(sr*2.1);y=stretch_bar(x,n);self.assertEqual(y.shape,(n,2))
  for i,f in enumerate([220,440]):
   frequency=np.fft.rfftfreq(n,1/sr)[np.argmax(np.abs(np.fft.rfft(y[:,i])))];self.assertLess(abs(frequency-f),2)
if __name__=='__main__':unittest.main()
