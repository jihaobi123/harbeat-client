import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_audio_preprocess.dj_structure_v2 import _combined_candidate_points, _phrase_boundaries_from_song, apply_dj_structure_analysis

class StructureTests(unittest.TestCase):
  def test_phrase_boundaries_prefer_persisted_structure(self):
    song=SimpleNamespace(phrase_map=[{"start_sec":16.0},{"start":8.0}])
    self.assertEqual(_phrase_boundaries_from_song(song,[0.0,1.0]),[8.0,16.0])

  def test_candidate_union_preserves_group_priority_and_limit(self):
    values=_combined_candidate_points([10.0,20.0],[20.0,30.0],[1.0,2.0],limit=4)
    self.assertEqual(len(values),4)
    self.assertEqual(values,sorted(set(values)))

  def test_apply_reuses_existing_v2_without_audio_decode(self):
    existing={"version":"dj_structure_v2","track1_exit_candidates":[1],"track2_entry_candidates":[2]}
    song=SimpleNamespace(music_features={"dj_structure_v2":existing},source_path="missing.wav")
    self.assertIs(apply_dj_structure_analysis(song),existing)
