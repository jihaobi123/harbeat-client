import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_sequence_planner.default_mix.playlist_selector import plan_default_sequence

def song(song_id,bpm,key,energy,low=.5):
  return SimpleNamespace(id=song_id,title=song_id,artist='test',bpm=bpm,key=key,camelot_key=None,energy=energy,beat_points=[i*60/bpm for i in range(32)],downbeats=[i*4*60/bpm for i in range(8)],phrase_map=[],duration=32*60/bpm,stems=None,music_features={'dj':{'low_ratio':low}},genre_profile={},loudness_profile={})

class DefaultSequenceTests(unittest.TestCase):
  def test_returns_every_song_once_when_pairs_are_compatible(self):
    result=plan_default_sequence([song('a',100,'C',.3),song('b',101,'C',.4),song('c',102,'G',.5)])
    ids=[row['song_id'] for row in result['sequence']]
    self.assertEqual(set(ids),{'a','b','c'}); self.assertEqual(len(ids),3)
    self.assertEqual(len(result['pair_scores']),2)

  def test_filters_bpm_incompatible_candidate_without_crashing(self):
    result=plan_default_sequence([song('a',100,'C',.3),song('b',101,'C',.4),song('far',150,'C',.5)])
    self.assertNotIn('far', [row['to_song_id'] for row in result['pair_scores']])

  def test_empty_input_is_explicit(self):
    self.assertEqual(plan_default_sequence([])['sequence'],[])
