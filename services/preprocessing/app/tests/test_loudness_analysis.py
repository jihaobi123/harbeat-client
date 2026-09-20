import json
import unittest

import numpy as np

from app.modules.library.analysis import _analyze_loudness


class LoudnessAnalysisTests(unittest.TestCase):
    def test_silence_reports_safe_fallback_values(self):
        profile = _analyze_loudness(np.zeros(22050, dtype=np.float32), 22050)

        self.assertEqual(profile["loudness_method"], "silence")
        self.assertEqual(profile["clip_ratio"], 0.0)
        self.assertEqual(profile["replay_gain_db"], 0.0)
        self.assertFalse(profile["clipping_risk"])

    def test_full_scale_signal_reports_clipping_risk(self):
        profile = _analyze_loudness(np.ones(22050, dtype=np.float32), 22050)

        self.assertAlmostEqual(profile["peak_dbfs"], 0.0, places=2)
        self.assertGreater(profile["clip_ratio"], 0.99)
        self.assertTrue(profile["clipping_risk"])
        self.assertLessEqual(profile["replay_gain_db"], -1.0)

    def test_replay_gain_keeps_one_db_of_peak_headroom(self):
        t = np.arange(22050, dtype=np.float32) / 22050
        audio = 0.1 * np.sin(2 * np.pi * 440 * t)

        profile = _analyze_loudness(audio, 22050)

        self.assertGreater(profile["replay_gain_db"], 0.0)
        self.assertLessEqual(profile["replay_gain_db"], 19.0)
        self.assertGreater(profile["crest_factor_db"], 2.5)
        json.dumps(profile)


if __name__ == "__main__":
    unittest.main()
