import copy,unittest
from scripts.prepare_vocal_endpoint_pack import validate_handover_sources
class PackTests(unittest.TestCase):
 def case(self):
  source=dict(vocalSha256='v',masterSha256='m',runId='r',manifestSha256='f')
  c=dict(plan={'window':dict(start=10,end=18)},sourceVerification={'a':dict(source),'b':dict(source)})
  a=dict(selected={'tailEnd':2},source=dict(source));b=dict(source=dict(source),report={'candidates':[],'rejected':[]})
  return c,a,b
 def test_incoming_tail_crossing_entry_is_rejected(self):
  c,a,b=self.case();b['report']['candidates']=[dict(start=9,seedEnd=9.6,tailEnd=10.4)]
  with self.assertRaisesRegex(ValueError,'incoming model activity'):validate_handover_sources(c,a,b)
 def test_incoming_source_mismatch_is_rejected(self):
  c,a,b=self.case();b['source']['vocalSha256']='other'
  with self.assertRaisesRegex(ValueError,'source mismatch'):validate_handover_sources(c,a,b)
 def test_safe_matching_sources_are_accepted(self):
  c,a,b=self.case();before=copy.deepcopy((c,a,b));validate_handover_sources(c,a,b);self.assertEqual((c,a,b),before)
if __name__=='__main__':unittest.main()
