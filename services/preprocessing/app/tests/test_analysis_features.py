import unittest

import numpy as np

from app.modules.library.analysis import (
    _build_bpm_curve,
    _build_energy_curve,
    _build_transition_windows,
    _summarize_beatgrid,
    _attach_phrase_energy,
)


class AnalysisFeatureTests(unittest.TestCase):
    def test_bpm_curve_reports_local_tempo_and_stability(self):
        steady = [i * 0.5 for i in range(64)]
        curve, stability = _build_bpm_curve(steady, window_beats=16, hop_beats=8)

        self.assertGreaterEqual(len(curve), 6)
        self.assertAlmostEqual(curve[0]["bpm"], 120.0, places=1)
        self.assertAlmostEqual(curve[-1]["bpm"], 120.0, places=1)
        self.assertGreater(stability, 0.98)

    def test_bpm_curve_exposes_local_tempo_change(self):
        first = [i * 0.5 for i in range(32)]
        second_start = first[-1] + 0.5
        second = [second_start + i * 0.6 for i in range(1, 33)]

        curve, stability = _build_bpm_curve(first + second, window_beats=16, hop_beats=8)
        bpms = [window["bpm"] for window in curve]

        self.assertGreater(max(bpms), 115.0)
        self.assertLess(min(bpms), 105.0)
        self.assertLess(stability, 0.98)

    def test_beatgrid_summary_accepts_stable_grid(self):
        beats = [i * 0.5 for i in range(96)]
        curve, stability = _build_bpm_curve(beats)

        summary = _summarize_beatgrid(beats, curve, stability)

        self.assertGreater(summary["beat_confidence"], 0.95)
        self.assertAlmostEqual(summary["beat_grid_interval"], 0.5, places=3)
        self.assertFalse(summary["beat_needs_review"])
        self.assertEqual(summary["beat_engines_used"], ["librosa"])

    def test_beatgrid_summary_flags_sparse_or_unstable_grid(self):
        sparse = _summarize_beatgrid([0.1, 1.0, 1.7], [], 0.2)

        self.assertLess(sparse["beat_confidence"], 0.5)
        self.assertTrue(sparse["beat_needs_review"])

        jittery = np.cumsum([0.4, 0.7] * 48).tolist()
        curve, stability = _build_bpm_curve(jittery)
        unstable = _summarize_beatgrid(jittery, curve, stability)

        self.assertLess(unstable["beat_confidence"], 0.72)
        self.assertTrue(unstable["beat_needs_review"])

    def test_energy_curve_preserves_quiet_and_loud_sections(self):
        sr = 100
        quiet = np.full(sr * 4, 0.05, dtype=np.float32)
        loud = np.full(sr * 4, 0.8, dtype=np.float32)

        curve = _build_energy_curve(np.concatenate([quiet, loud]), sr, window_sec=2.0, hop_sec=2.0)

        self.assertEqual(len(curve), 4)
        self.assertLess(curve[0]["energy"], curve[-1]["energy"])
        self.assertLess(curve[0]["relative_energy"], 0.2)
        self.assertGreater(curve[-1]["relative_energy"], 0.9)

    def test_transition_windows_prefer_intro_for_entry_and_outro_for_exit(self):
        phrase_map = [
            {"start": 0.0, "end": 16.0, "label": "intro", "bars": 8, "energy": 0.2},
            {"start": 16.0, "end": 48.0, "label": "verse", "bars": 16, "energy": 0.6},
            {"start": 48.0, "end": 64.0, "label": "drop", "bars": 8, "energy": 1.0},
            {"start": 64.0, "end": 80.0, "label": "outro", "bars": 8, "energy": 0.25},
        ]

        windows = _build_transition_windows(phrase_map)

        self.assertEqual(windows[0]["label"], "intro")
        self.assertGreater(windows[0]["mix_in_score"], windows[0]["mix_out_score"])
        self.assertEqual(windows[-1]["label"], "outro")
        self.assertGreater(windows[-1]["mix_out_score"], windows[-1]["mix_in_score"])
        self.assertTrue(windows[0]["clean_candidate"])
        self.assertTrue(windows[-1]["clean_candidate"])

    def test_attach_phrase_energy_uses_overlapping_energy_windows(self):
        phrases = [
            {"start": 0.0, "end": 4.0, "label": "intro"},
            {"start": 4.0, "end": 8.0, "label": "drop"},
        ]
        energy_curve = [
            {"start": 0.0, "end": 2.0, "relative_energy": 0.2},
            {"start": 2.0, "end": 4.0, "relative_energy": 0.3},
            {"start": 4.0, "end": 6.0, "relative_energy": 0.9},
            {"start": 6.0, "end": 8.0, "relative_energy": 1.0},
        ]

        enriched = _attach_phrase_energy(phrases, energy_curve)

        self.assertAlmostEqual(enriched[0]["energy"], 0.25)
        self.assertAlmostEqual(enriched[1]["energy"], 0.95)


if __name__ == "__main__":
    unittest.main()
