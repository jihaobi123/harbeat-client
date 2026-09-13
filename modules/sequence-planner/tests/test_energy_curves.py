import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_sequence_planner.sequencer import PRESETS, sequence_songs, sequence_songs_with_details
from harbeat_sequence_planner.presets import resolve_preset

def song(song_id,energy):
  return SimpleNamespace(id=song_id,bpm=100,energy=energy,beat_points=[0,.6,1.2,1.8,2.4,3],downbeats=[0,2.4],phrase_map=[],duration=4,stems=None)

class EnergyCurveTests(unittest.TestCase):
  def test_all_presets_return_unique_song_ids(self):
    songs=[song(str(i),i/10) for i in range(1,7)]
    for preset in PRESETS:
      with self.subTest(preset=preset):
        result=sequence_songs_with_details(songs,preset)
        ids=[row['song_id'] for row in result['sequence']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(set(ids),set(str(i) for i in range(1,7)))

  def test_unknown_preset_is_normalized_by_legacy_behavior(self):
    result=sequence_songs([song('a',.3),song('b',.8)],'unknown')
    self.assertEqual(len(result),2)

  def test_unknown_preset_resolution_is_observable(self):
    result=sequence_songs_with_details([song('a',.3),song('b',.8)],'unknown')
    self.assertEqual(result['ordering_mode'],'battle_4rounds')
    self.assertEqual(result['preset_resolution']['reason'],'unknown_preset_normalized')

  def test_compatibility_preset_is_explicit(self):
    resolution=resolve_preset('battle')
    self.assertEqual(resolution.resolved,'battle'); self.assertTrue(resolution.compatibility_used)
