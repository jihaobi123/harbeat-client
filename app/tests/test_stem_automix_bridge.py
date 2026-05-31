import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.modules.playlists.stem_automix_integration import library_song_to_track_context


class StemAutomixBridgeTests(unittest.TestCase):
    def test_bridge_uses_real_stem_analysis_values(self):
        song = SimpleNamespace(
            id="song-1",
            bpm=124.0,
            camelot_key="8A",
            energy=0.82,
            duration=210.0,
            beat_points=[0.0, 0.5],
            downbeats=[0.0],
            phrase_map=[],
            cue_points=[],
            stems={"vocals": "v.wav", "drums": "d.wav", "bass": "b.wav", "other": "o.wav"},
            stem_quality_score=0.93,
            stem_activity={"vocals": 0.22, "drums": 0.84, "bass": 0.61, "other": 0.3},
            intro_is_clean=True,
            outro_is_clean=False,
            has_drum_loop=True,
        )

        context = library_song_to_track_context(song)

        self.assertEqual(context.energy, "high")
        self.assertEqual(context.stem_quality_score, 0.93)
        self.assertEqual(context.vocal_density, 0.22)
        self.assertEqual(context.bass_energy, 0.61)
        self.assertTrue(context.intro_is_clean)
        self.assertFalse(context.outro_is_clean)
        self.assertTrue(context.has_drum_loop)


if __name__ == "__main__":
    unittest.main()
