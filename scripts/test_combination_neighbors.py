import copy,unittest
from prepare_combination_neighbors import make_filter,eligible_alignment
class FilterEvidenceTests(unittest.TestCase):
 def source(self):
  c={'plan':{'from':'a','start':10,'end':18},'timing':{'swapEnd':6},'sourceVerification':{'a':{'runId':'r','masterSha256':'m'}}}
  source={'reportId':'report','reportSha256':'report-sha','masterSha256':'m','vocalSha256':'v'}
  t={'id':'a','provenance':{'runId':'r',**source},'alignment':{'source':source,'bars':[{'start':16,'end':18,'beats':[16,16.5,17,17.5],'valid':True}]}}
  return c,t
 def test_accepts_fixed_observed_bar_without_mutating_source_or_timing(self):
  c,t=self.source();old=copy.deepcopy((c,t));f=make_filter(c,t);self.assertEqual(f['sourceStart'],16);self.assertEqual((f['startHz'],f['endHz']), (20,1800));self.assertEqual((c,t),old)
 def test_rejects_shifted_timing_incomplete_bar_or_unbound_source(self):
  for kind in ['timing','bar','source','track','run']:
   c,t=self.source()
   if kind=='timing':c['timing']['swapEnd']+=.2
   if kind=='bar':t['alignment']['bars'][0]['valid']=False
   if kind=='source':t['alignment']['source']['vocalSha256']='wrong'
   if kind=='track':t['id']='wrong'
   if kind=='run':t['provenance']['runId']='wrong'
   with self.subTest(kind=kind),self.assertRaises(ValueError):make_filter(c,t)
class ProbeGateTests(unittest.TestCase):
 def test_rejects_mismatched_probe_without_relaxing_tolerance(self):
  self.assertTrue(eligible_alignment({'aMaster':0.,'aBass':0.}))
  self.assertFalse(eligible_alignment({'aMaster':1.8,'aBass':.9}))
  self.assertFalse(eligible_alignment({'aMaster':0.,'aBass':.002}))
  self.assertFalse(eligible_alignment({'aMaster':float('nan'),'aBass':0.}))
if __name__=='__main__':unittest.main()
