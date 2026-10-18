import unittest
from prepare_drum_loop import pick_profiles
class TestSelection(unittest.TestCase):
 def test_reserves_a_stable_contrast_when_a_thinning_source_is_also_the_only_control(self):
  rows=[{'caseId':'a-thin','eligible':True,'category':'thinning','metrics':{'ratio':.1}},{'caseId':'b-thin','eligible':True,'category':'thinning','metrics':{'ratio':.2}},{'caseId':'a-stable','eligible':True,'category':'stable','metrics':{'ratio':1}}]
  result=pick_profiles(rows,{'a-thin':'a','b-thin':'b','a-stable':'a'})
  self.assertEqual({r['caseId'] for r in result},{'b-thin','a-stable'})
 def test_prefers_complete_two_thinning_plus_control_cohort_when_available(self):
  rows=[{'caseId':'a-thin','eligible':True,'category':'thinning','metrics':{'ratio':.1}},{'caseId':'b-thin','eligible':True,'category':'thinning','metrics':{'ratio':.2}},{'caseId':'a-stable','eligible':True,'category':'stable','metrics':{'ratio':1}},{'caseId':'c-stable','eligible':True,'category':'stable','metrics':{'ratio':1.05}}]
  result=pick_profiles(rows,{'a-thin':'a','b-thin':'b','a-stable':'a','c-stable':'c'})
  self.assertEqual({r['caseId'] for r in result},{'a-thin','b-thin','c-stable'})
if __name__=='__main__':unittest.main()
