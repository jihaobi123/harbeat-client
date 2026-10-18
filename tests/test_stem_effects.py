import copy,unittest
import numpy as np
from analysis_platform.stem_effects import plan_vocal_echo,finite_taps,render_vocal_echo
class StemEffectTests(unittest.TestCase):
 def inputs(self):
  source=dict(vocalSha256='v',masterSha256='m',runId='r',manifestSha256='f')
  c=dict(pre=4,bpm=[120,120],plan=dict(start=10,end=18,duration=8,rate=1,window=dict(start=20,end=28)),sourceVerification={'a':dict(source),'b':dict(source)})
  a=dict(source=dict(source),coverage=dict(start=5,end=24),selected=dict(start=11,tailEnd=16,nextOnset=23,nextOnsetObserved=False,fadeStart=16.5,fadeEnd=16.7))
  b=dict(source=dict(source),coverage=dict(start=18,end=31),report=dict(candidates=[],rejected=[]))
  return c,a,b
 def test_safe_finite_effect_with_frozen_mapping(self):
  c,a,b=self.inputs();before=copy.deepcopy((c,a,b));r=plan_vocal_echo(c,a,b)
  self.assertEqual([x['delaySeconds'] for x in r['taps']],[.25,.5,.75]);self.assertLess(r['wetEnd'],12-.08);self.assertEqual(r['sendEnd'],10);self.assertEqual((c,a,b),before)
 def test_too_late_tail_is_rejected(self):
  c,a,b=self.inputs();a['selected']['tailEnd']=17.4
  with self.assertRaisesRegex(ValueError,'quiet-window'):plan_vocal_echo(c,a,b)
 def test_reentry_and_missing_observations_are_rejected(self):
  c,a,b=self.inputs();a['selected']['nextOnset']=16.5
  with self.assertRaises(ValueError):plan_vocal_echo(c,a,b)
  c,a,b=self.inputs();b['coverage']['end']=25
  with self.assertRaises(ValueError):plan_vocal_echo(c,a,b)
 def test_incoming_tail_in_effect_window_is_rejected(self):
  c,a,b=self.inputs();b['report']['rejected']=[dict(start=25,tailEnd=27,reason='uncertain')]
  with self.assertRaisesRegex(ValueError,'incoming'):plan_vocal_echo(c,a,b)
 def test_source_and_tempo_invalid(self):
  for change in ['source','tempo','rate']:
   c,a,b=self.inputs()
   if change=='source':b['source']['vocalSha256']='wrong'
   if change=='tempo':c['bpm'][0]=float('nan')
   if change=='rate':c['plan']['rate']=0
   with self.assertRaises(ValueError):plan_vocal_echo(c,a,b)
 def test_impulse_has_only_three_finite_taps(self):
  x=np.zeros((100,2));x[10]=[1,-1];y=finite_taps(x,100,[dict(delaySeconds=.1,gain=.26),dict(delaySeconds=.2,gain=.117),dict(delaySeconds=.3,gain=.052)])
  self.assertEqual(np.flatnonzero(y[:,0]).tolist(),[20,30,40]);np.testing.assert_allclose(y[[20,30,40],0],[.26,.117,.052]);np.testing.assert_array_equal(y[:,0],-y[:,1]);self.assertEqual(x[10,0],1)
 def test_silence_stays_silent(self):
  c,a,b=self.inputs();fx=plan_vocal_echo(c,a,b);y=render_vocal_echo(np.zeros((192000,2)),16000,fx);self.assertFalse(y.any())
 def test_render_is_local_finite_and_preserves_input(self):
  c,a,b=self.inputs();fx=plan_vocal_echo(c,a,b);sr=16000;t=np.arange(sr*12)/sr;x=np.column_stack([np.sin(2*np.pi*500*t)]*2);before=x.copy();y=render_vocal_echo(x,sr,fx)
  self.assertGreater(np.max(abs(y)),.01);self.assertFalse(y[:int(fx['wetStart']*sr)-1].any());self.assertFalse(y[int(fx['wetEnd']*sr)+1:].any());np.testing.assert_array_equal(x,before);self.assertTrue(np.isfinite(y).all())
if __name__=='__main__':unittest.main()
