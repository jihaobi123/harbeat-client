import os
import tempfile
import unittest
from unittest.mock import patch

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

            with patch.dict(os.environ, {"FEATURE_DRUM_TRANSCRIBER_COMMAND": ""}):
                result = analyze_stem_files(
                    paths,
                    original_path=original_path,
                    window_sec=2.0,
                    bpm=120.0,
                    beat_points=np.arange(0.0, duration, 0.5).tolist(),
                    downbeats=np.arange(0.0, duration + 0.01, 2.0).tolist(),
                )

        self.assertEqual(len(result["stem_activity_windows"]), 4)
        self.assertLess(result["stem_activity_windows"][0]["vocals"], 0.1)
        self.assertGreater(result["stem_activity_windows"][-1]["vocals"], 0.8)
        self.assertTrue(result["intro_is_clean"])
        self.assertFalse(result["outro_is_clean"])
        self.assertGreater(result["intro_clean_score"], 0.7)
        self.assertLess(result["outro_clean_score"], 0.3)
        self.assertTrue(result["has_drum_loop"])
        self.assertGreater(result["drum_loop_analysis"]["score"], 0.62)
        self.assertEqual(
            result["drum_loop_analysis"]["method"],
            "bar_aligned_log_mel_self_similarity_v1",
        )
        self.assertIn(
            "sampled_loop_tendency",
            result["feature_analysis"]["feature_groups"]["production"],
        )
        sampled = result["feature_analysis"]["feature_groups"]["production"]["sampled_loop_tendency"]
        self.assertEqual(sampled["validation_status"], "candidate_only")
        self.assertFalse(sampled["style_required_allowed"])
        self.assertIn("drum_analysis", result)
        self.assertIn("feature_analysis", result)
        self.assertEqual(result["feature_analysis"]["version"], "pre_style_evidence_v5")
        self.assertIn("feature_groups", result["feature_analysis"])
        self.assertIn("analysis_modules", result["feature_analysis"])
        self.assertIn("rhythm_grammar", result["feature_analysis"]["feature_groups"])
        self.assertIn("low_frequency", result["feature_analysis"]["feature_groups"])
        self.assertIn("percussion_timbre", result["feature_analysis"]["feature_groups"])
        self.assertIn("production", result["feature_analysis"]["feature_groups"])
        self.assertIn("mature_models_unavailable_using_dsp_fallbacks", result["feature_analysis"]["quality_flags"])
        self.assertGreater(result["stem_quality_score"], 0.9)
        self.assertEqual(result["stem_quality_profile"]["completeness"], 1.0)
        self.assertGreater(result["stem_quality_profile"]["reconstruction_score"], 0.9)
        self.assertGreater(result["stem_quality_profile"]["reconstruction_quality"], 0.9)
        self.assertEqual(
            result["stem_quality_profile"]["reconstruction_method"],
            "waveform_reconstruction",
        )
        self.assertIsNone(result["stem_quality_profile"]["separation_reliability"])
        self.assertEqual(result["stem_quality_profile"]["quality_status"], "reconstruction_only")

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
        self.assertIsNone(result["stem_quality_profile"]["reconstruction_quality"])
        self.assertEqual(
            result["stem_quality_profile"]["reconstruction_method"],
            "original_audio_unavailable",
        )
        self.assertFalse(result["has_drum_loop"])
        self.assertEqual(result["drum_analysis"]["status"], "unavailable")
        self.assertIn("feature_analysis", result)


if __name__ == "__main__":
    unittest.main()
