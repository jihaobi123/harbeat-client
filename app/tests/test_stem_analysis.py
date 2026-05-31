import os
import tempfile
import unittest

import numpy as np
import soundfile as sf

from app.modules.library.stem_analysis import analyze_stem_files


class StemAnalysisTests(unittest.TestCase):
    def test_stem_analysis_detects_clean_intro_and_active_outro(self):
        sr = 1000
        duration = 8
        samples = sr * duration
        t = np.arange(samples) / sr

        drums = 0.35 * np.sin(2 * np.pi * 4 * t)
        bass = 0.25 * np.sin(2 * np.pi * 60 * t)
        vocals = np.zeros(samples)
        vocals[sr * 2:] = 0.45 * np.sin(2 * np.pi * 220 * t[sr * 2:])
        other = 0.12 * np.sin(2 * np.pi * 440 * t)
        original = drums + bass + vocals + other

        with tempfile.TemporaryDirectory() as td:
            paths = {}
            for name, audio in {
                "vocals": vocals,
                "drums": drums,
                "bass": bass,
                "other": other,
            }.items():
                path = os.path.join(td, f"{name}.wav")
                sf.write(path, audio, sr)
                paths[name] = path
            original_path = os.path.join(td, "original.wav")
            sf.write(original_path, original, sr)

            result = analyze_stem_files(paths, original_path=original_path, window_sec=2.0)

        self.assertEqual(len(result["stem_activity_windows"]), 4)
        self.assertLess(result["stem_activity_windows"][0]["vocals"], 0.1)
        self.assertGreater(result["stem_activity_windows"][-1]["vocals"], 0.8)
        self.assertTrue(result["intro_is_clean"])
        self.assertFalse(result["outro_is_clean"])
        self.assertGreater(result["intro_clean_score"], 0.7)
        self.assertLess(result["outro_clean_score"], 0.3)
        self.assertTrue(result["has_drum_loop"])
        self.assertGreater(result["stem_quality_score"], 0.9)
        self.assertEqual(result["stem_quality_profile"]["completeness"], 1.0)
        self.assertGreater(result["stem_quality_profile"]["reconstruction_score"], 0.9)

    def test_stem_analysis_degrades_when_required_stem_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "vocals.wav")
            sf.write(path, np.zeros(2000), 1000)

            result = analyze_stem_files({"vocals": path}, window_sec=2.0)

        self.assertFalse(result["has_complete_stems"])
        self.assertLess(result["stem_quality_score"], 0.4)
        self.assertEqual(result["intro_clean_score"], 0.0)
        self.assertEqual(result["outro_clean_score"], 0.0)
        self.assertEqual(result["stem_quality_profile"]["completeness"], 0.25)
        self.assertFalse(result["has_drum_loop"])


if __name__ == "__main__":
    unittest.main()
