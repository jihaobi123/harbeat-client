import copy, unittest
from analysis_platform.vocal_endpoints import detect_endpoints, select_exit

class EndpointTests(unittest.TestCase):
 def frames(self, spans, pitch=None, model=True):
  return [dict(t=i*.05,rms=.2 if any(a<=i*.05<b for a,b in spans) else .0001,voiced=.9 if pitch and any(a<=i*.05<b for a,b in pitch) else 0,voice=.95 if model else .1) for i in range(201)]
 def test_energy_only_does_not_seed_voice(self):
  self.assertEqual(detect_endpoints(self.frames([(1,3)],model=False),[])['candidates'],[])
 def test_short_breath_is_joined(self):
  r=detect_endpoints(self.frames([(1,2),(2.2,3)]),[[1,3]])
  self.assertEqual(len(r['candidates']),1);self.assertGreaterEqual(r['candidates'][0]['tailEnd'],3)
 def test_long_gap_retained(self):
  r=detect_endpoints(self.frames([(1,2),(3,4)]),[[1,2],[3,4]])
  self.assertEqual(len(r['candidates']),2)
 def test_pitch_tail_is_protected_only_near_voice(self):
  f=self.frames([(1,2)],[(1,2.6)])
  for x in f:
   if 2<=x['t']<2.6:x['rms']=.002
  r=detect_endpoints(f,[[1,2]])
  self.assertGreaterEqual(r['candidates'][0]['tailEnd'],2.6)
 def test_unsettled_tail_rejected(self):
  f=self.frames([(1,2)],[(1,5)])
  for x in f:
   if 2<=x['t']<5:x['rms']=.002;x['voice']=.1
  r=detect_endpoints(f,[[1,2]])
  self.assertTrue(any(x['reason']=='tail-unsettled' for x in r['rejected']))
 def test_next_onset_and_cue_guard(self):
  r=detect_endpoints(self.frames([(1,2),(2.7,4)]),[[1,2],[2.7,4]])
  self.assertIsNone(select_exit(r,1,3,[2.5,3],.3))
 def test_select_safe_beat_in_gap(self):
  r=detect_endpoints(self.frames([(1,2),(5,6)]),[[1,2],[5,6]])
  x=select_exit(r,1,4,[2.5,3,3.5],.25)
  self.assertIsNotNone(x);self.assertGreaterEqual(x['fadeStart'],x['tailEnd']);self.assertLessEqual(x['fadeEnd'],4)
 def test_quiet_later_vad_cannot_be_ignored(self):
  f=self.frames([(1,2)])
  for x in f:
   if 3<=x['t']<4:x['rms']=.002;x['voiced']=.9
  r=detect_endpoints(f,[[1,2],[3,4]])
  self.assertIsNone(select_exit(r,1,3.5,[2.5,3],.2))
 def test_quiet_pitched_model_reentry_even_without_vad(self):
  f=self.frames([(1,2)])
  for x in f:
   if 3<=x['t']<4:x['rms']=.002;x['voiced']=.9
  self.assertIsNone(select_exit(detect_endpoints(f,[[1,2]]),1,3.5,[2.5,3],.2))
 def test_low_unvoiced_vad_tail_is_kept(self):
  r=detect_endpoints(self.frames([(1,2)]),[[1,2.4]])
  self.assertGreaterEqual(r['candidates'][0]['tailEnd'],2.4)
 def test_pitch_after_extended_vad_tail_cannot_escape_quiet_check(self):
  f=self.frames([(1,2)],model=False)
  for x in f:
   if 1<=x['t']<2:x['voice']=.95
   if 2.4<=x['t']<2.7:x['rms']=.002;x['voiced']=.9
  self.assertIsNone(select_exit(detect_endpoints(f,[[1,2.4]]),1,4,[2.5,3,3.5],.2))
 def test_missing_invalid_no_mutation(self):
  with self.assertRaises(ValueError):detect_endpoints([],[])
  f=self.frames([(1,2)]);before=copy.deepcopy(f);detect_endpoints(f,[[1,2]]);self.assertEqual(f,before)
if __name__=='__main__':unittest.main()
