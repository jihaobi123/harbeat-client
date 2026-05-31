import unittest
from types import SimpleNamespace

from app.modules.dj_control.dance_style import score_song_combined
from app.modules.library.dj_feature_extractor import rhythm_features


class DjFingerprintTests(unittest.TestCase):
    def test_rhythm_features_reports_stable_four_on_floor_grid(self):
        beats = [i * 0.5 for i in range(64)]
        downbeats = beats[::4]

        features = rhythm_features(beats, downbeats, duration=32.0, bpm=120.0)

        self.assertAlmostEqual(features["beat_density"], 2.0)
        self.assertGreater(features["downbeat_consistency"], 0.99)
        self.assertGreater(features["four_on_floor"], 0.99)
        self.assertLess(features["groove_complexity"], 0.01)

    def test_combined_style_scorer_prefers_v3_features_when_present(self):
        song = SimpleNamespace(
            bpm=124.0,
            energy=0.75,
            duration=210.0,
            beat_points=[i * 0.5 for i in range(420)],
            downbeats=[i * 2.0 for i in range(105)],
            phrase_map=[],
            music_features={"dj": {
                "bpm": 124.0,
                "energy": 0.75,
                "beat_density": 2.0,
                "four_on_floor": 0.98,
                "downbeat_consistency": 0.99,
                "drums_to_vocals_ratio": 2.5,
                "spectral_rolloff": 7000.0,
                "groove_complexity": 0.04,
            }},
        )

        house_score, source, breakdown = score_song_combined(song, "house")
        hiphop_score, _, _ = score_song_combined(song, "hiphop")

        self.assertEqual(source, "v3")
        self.assertGreater(house_score, 0.9)
        self.assertGreater(house_score, hiphop_score)
        self.assertGreater(breakdown["four_on_floor"], 0.9)


if __name__ == "__main__":
    unittest.main()
