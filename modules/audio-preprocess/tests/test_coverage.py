import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_audio_preprocess.coverage import inspect_payloads

def payload():
  return {"version":"dj_structure_v2","source":"harbeat_dj_structure_analysis_v2","track1_exit_candidates":[{"type":"track1_exit_candidate","time":10.0,"score":0.7,"audio_feature_source":"dj_structure_precomputed_window_v2"}],"track2_entry_candidates":[{"type":"track2_entry_candidate","time":8.0,"score":0.8,"audio_feature_source":"dj_structure_precomputed_window_v2"}]}

class CoverageTests(unittest.TestCase):
  def test_accounts_for_ready_missing_and_invalid_rows(self):
    report = inspect_payloads([("a",payload()),("b",None),("c",{"version":"old"})])
    self.assertEqual(report.total, 3)
    self.assertEqual(report.ready, 1)
    self.assertEqual(report.missing, ("b",))
    self.assertEqual(report.invalid, ("c",))
    self.assertFalse(report.complete)
