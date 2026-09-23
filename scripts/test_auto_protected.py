import unittest
from build_auto_protected import quiet_ranges
class QuietTests(unittest.TestCase):
 def test_gap_does_not_bridge_loud_frame_or_missing_time(self):
  p=[{'start':i*.05,'end':(i+1)*.05,'rms_dbfs':(-10 if i==2 else -40)} for i in range(7)]
  self.assertEqual(len(quiet_ranges(p)),1);self.assertAlmostEqual(quiet_ranges(p)[0]['start'],.15)
 def test_unknown_or_loud_not_silence(self):
  self.assertEqual(quiet_ranges([{'start':0,'end':.4,'rms_dbfs':-20}]),[])
if __name__=='__main__':unittest.main()
