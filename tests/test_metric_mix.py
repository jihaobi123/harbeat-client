import math,unittest
import numpy as np
from metric_mix.policy import choose_method
from metric_mix.render import mix_candidates

class MetricPolicyTest(unittest.TestCase):
 def base(self,**kw):return dict(bassOverlap=.0,otherOverlap=.0,bassDifference=.0,otherDifference=.0,vocalBenefit=.0,stemAvailable={'bass':True,'other':True,'vocals':True},vocalSafe=False,**kw)
 def test_missing_evidence_does_not_become_zero_or_trigger_an_effect(self):
  m=self.base();m['bassOverlap']=None;m['otherOverlap']=None
  r=choose_method(m);self.assertEqual(r['recommended'],'original');self.assertEqual(r['methods']['bass']['eligible'],False)
 def test_nonfinite_evidence_is_rejected(self):
  m=self.base();m['bassOverlap']=math.nan
  with self.assertRaises(ValueError):choose_method(m)
 def test_no_problem_keeps_original(self):self.assertEqual(choose_method(self.base())['recommended'],'original')
 def test_strong_other_evidence_can_select_filter_without_bass(self):
  m=self.base();m.update(otherOverlap=.8,otherDifference=.3)
  r=choose_method(m);self.assertEqual(r['recommended'],'filter');self.assertFalse(r['methods']['bass']['eligible'])
 def test_combination_needs_a_margin_over_both_singles(self):
  m=self.base();m.update(otherOverlap=.8,otherDifference=.3,bassOverlap=.8,bassDifference=.7)
  r=choose_method(m);self.assertEqual(r['recommended'],'bass_filter');self.assertGreaterEqual(r['methods']['bass_filter']['score']-max(r['methods'][k]['score'] for k in ['bass','filter']),r['policy']['combinationMargin'])
 def test_combination_cannot_depend_on_peak_rejected_singles(self):
  m=self.base();m.update(otherOverlap=.8,otherDifference=.3,bassOverlap=.8,bassDifference=.7)
  r=choose_method(m,{'bass':{'peak':1.01},'filter':{'peak':1.01},'bass_filter':{'peak':.8}})
  self.assertFalse(r['methods']['bass_filter']['eligible']);self.assertEqual(r['recommended'],'original')
 def test_missing_stem_excludes_dependent_methods(self):
  m=self.base();m.update(otherOverlap=.8,otherDifference=.3,bassOverlap=.8,bassDifference=.7);m['stemAvailable']['bass']=False
  r=choose_method(m);self.assertFalse(r['methods']['bass_filter']['eligible']);self.assertEqual(r['recommended'],'filter')

class RenderTest(unittest.TestCase):
 def fixture(self):
  sr=44100;d=4;n=sr*d;t=np.arange(n)/sr
  a=np.stack([np.sin(2*np.pi*f*t)*.1 for f in [110,220,440,1760]],axis=1);b=np.stack([np.sin(2*np.pi*f*t)*.1 for f in [147,294,587,2200]],axis=1)
  a=np.repeat(a[:,:,None],2,axis=2);b=np.repeat(b[:,:,None],2,axis=2)
  stems={'a':{'bass':a[:,0],'drums':a[:,1],'vocals':a[:,2],'other':a[:,3]},'b':{'bass':b[:,0],'drums':b[:,1],'vocals':b[:,2],'other':b[:,3]}}
  for s in stems.values():s['master']=sum(s.values())
  c={'duration':d,'lastBarStart':2,'bassTiming':{'duckStart':1,'swapStart':2.5,'swapEnd':3},'vocalExit':None,'eq':None,'body':np.ones((16,2))*.1}
  return stems,c,sr
 def test_combo_is_exact_sum_of_independent_corrections(self):
  stems,c,sr=self.fixture();o=mix_candidates(stems,c,sr)
  np.testing.assert_allclose(o['bass_filter']-o['filter'],o['bass']-o['original'],atol=2e-7)
  self.assertTrue(all(np.isfinite(x).all() for x in o.values()))
 def test_all_return_to_same_original_at_takeover(self):
  stems,c,sr=self.fixture();o=mix_candidates(stems,c,sr)
  for x in o.values():np.testing.assert_allclose(x[-16:],np.ones((16,2))*.06,atol=1e-7)
 def test_original_independent_of_unsupported_voice_option(self):
  stems,c,sr=self.fixture();o=mix_candidates(stems,c,sr);self.assertNotIn('vocal',o)

if __name__=='__main__':unittest.main()
