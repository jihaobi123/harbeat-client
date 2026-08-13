import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_audio_preprocess.version_gate import AnalysisGateError, validate_dj_structure_v2
from test_coverage import payload

class GateTests(unittest.TestCase):
  def test_accepts_v2_candidate_payload(self):
    validate_dj_structure_v2(payload())

  def test_rejects_missing_candidates(self):
    bad=payload(); bad["track1_exit_candidates"]=[]
    with self.assertRaises(AnalysisGateError): validate_dj_structure_v2(bad)

  def test_rejects_nan_candidate(self):
    bad=payload(); bad["track1_exit_candidates"][0]["score"]=math.nan
    with self.assertRaises(AnalysisGateError): validate_dj_structure_v2(bad)
