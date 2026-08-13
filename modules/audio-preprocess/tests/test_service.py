import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harbeat_audio_preprocess.service import PreprocessService


def payload():
  base={"audio_feature_source":"dj_structure_precomputed_window_v2","time":4.0,"score":0.8}
  return {"version":"dj_structure_v2","source":"harbeat_dj_structure_analysis_v2","track1_exit_candidates":[{"type":"track1_exit_candidate",**base}],"track2_entry_candidates":[{"type":"track2_entry_candidate",**base}]}


class MemoryRepository:
  def __init__(self,features=None): self.features=features or {}; self.saves=0
  def load_features(self,song_id): return self.features
  def save_features(self,song_id,features): self.features=dict(features); self.saves+=1


class ServiceTests(unittest.TestCase):
  def test_reuses_valid_version_without_analyzing_or_saving(self):
    repo=MemoryRepository({"dj_structure_v2":payload()}); calls=[]
    result=PreprocessService(repo,lambda song_id:calls.append(song_id)).process('song-1')
    self.assertTrue(result.reused); self.assertEqual(calls,[]); self.assertEqual(repo.saves,0)

  def test_validates_and_persists_new_payload(self):
    repo=MemoryRepository({"other":{"kept":True}})
    result=PreprocessService(repo,lambda song_id:payload()).process('song-1')
    self.assertFalse(result.reused); self.assertEqual(repo.saves,1)
    self.assertIn('other',repo.features); self.assertIn('dj_structure_v2',repo.features)

  def test_invalid_analyzer_payload_is_not_persisted(self):
    repo=MemoryRepository()
    with self.assertRaises(ValueError): PreprocessService(repo,lambda song_id:{"version":"bad"}).process('song-1')
    self.assertEqual(repo.saves,0)
