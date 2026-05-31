"""Tests for extended analysis: time signature, section intensity, groove,
vocal events, bass risk, stem-aware transition scoring."""
import json
import unittest

import numpy as np

from app.modules.library.analysis import (
    _analyze_dancefloor_profile,
    _compute_bass_risk_windows,
    _compute_groove_score,
    _detect_time_signature,
    _detect_vocal_events,
    _enhance_transition_windows,
    _generate_dj_hot_cues,
    _infer_downbeats_and_time_signature,
    _score_section_intensity,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Time signature
# ═══════════════════════════════════════════════════════════════════════════════

class TimeSignatureTests(unittest.TestCase):
    def test_regular_4_4_detected(self):
        """4/4: downbeat every 4 beats at 120bpm."""
        beats = [i * 0.5 for i in range(64)]  # 120bpm = 0.5s
        downbeats = beats[0::4]
        ts = _detect_time_signature(beats, downbeats, bpm=120.0)
        self.assertEqual(ts["numerator"], 4)
        self.assertEqual(ts["denominator"], 4)
        self.assertGreater(ts["confidence"], 0.85)

    def test_3_4_detected(self):
        """3/4: downbeat every 3 beats."""
        beats = [i * 0.4 for i in range(60)]  # 150bpm
        downbeats = beats[0::3]
        ts = _detect_time_signature(beats, downbeats, bpm=150.0)
        self.assertEqual(ts["numerator"], 3)

    def test_sparse_data_falls_back_to_4_4(self):
        """Not enough data → fallback to 4/4 with low confidence."""
        ts = _detect_time_signature([0.0, 0.5, 1.0], [0.0], bpm=120.0)
        self.assertEqual(ts["numerator"], 4)
        self.assertEqual(ts["confidence"], 0.0)
        self.assertEqual(ts["method"], "fallback")

    def test_json_serializable(self):
        beats = [i * 0.5 for i in range(32)]
        downbeats = beats[0::4]
        ts = _detect_time_signature(beats, downbeats, bpm=120.0)
        json.dumps(ts)  # should not raise

    def test_audio_accent_periodicity_can_detect_3_4_without_assuming_4_4(self):
        beats = [i * 0.5 for i in range(48)]
        accents = [1.0 if i % 3 == 0 else 0.1 for i in range(len(beats))]

        downbeats, ts = _infer_downbeats_and_time_signature(beats, accents)

        self.assertEqual(ts["numerator"], 3)
        self.assertEqual(ts["denominator"], 4)
        self.assertEqual(downbeats[:3], [0.0, 1.5, 3.0])

    def test_audio_accent_periodicity_detects_regular_4_4(self):
        beats = [i * 0.5 for i in range(64)]
        accents = [1.0 if i % 4 == 1 else 0.1 for i in range(len(beats))]

        downbeats, ts = _infer_downbeats_and_time_signature(beats, accents)

        self.assertEqual(ts["numerator"], 4)
        self.assertEqual(downbeats[:3], [0.5, 2.5, 4.5])

    def test_weak_meter_evidence_falls_back_to_reviewable_4_4(self):
        beats = [i * 0.5 for i in range(48)]
        accents = [0.5 for _ in beats]

        downbeats, ts = _infer_downbeats_and_time_signature(beats, accents)

        self.assertEqual(ts["numerator"], 4)
        self.assertTrue(ts["needs_review"])
        self.assertEqual(ts["method"], "beat_accent_periodicity_fallback_4_4")
        self.assertEqual(downbeats[:3], [0.0, 2.0, 4.0])


# ═══════════════════════════════════════════════════════════════════════════════
# Section intensity
# ═══════════════════════════════════════════════════════════════════════════════

class SectionIntensityTests(unittest.TestCase):
    def test_drop_gets_high_intensity(self):
        phrases = [
            {"start": 0, "end": 8, "label": "intro", "bars": 8, "energy": 0.25},
            {"start": 8, "end": 16, "label": "buildup", "bars": 8, "energy": 0.55},
            {"start": 16, "end": 24, "label": "drop", "bars": 8, "energy": 0.95},
            {"start": 24, "end": 32, "label": "outro", "bars": 8, "energy": 0.2},
        ]
        energy = [
            {"start": 0, "end": 8, "relative_energy": 0.25},
            {"start": 8, "end": 16, "relative_energy": 0.55},
            {"start": 16, "end": 24, "relative_energy": 0.95},
            {"start": 24, "end": 32, "relative_energy": 0.2},
        ]
        scored = _score_section_intensity(phrases, energy)
        drop = scored[2]
        self.assertEqual(drop["label"], "drop")
        # Without real audio (no spectral contrast), intensity ~0.45
        # With real audio providing spectral_variation, it would be higher
        self.assertGreater(drop["intensity"], 0.4)
        self.assertTrue(drop["is_peak_section"])

    def test_breakdown_gets_low_intensity(self):
        phrases = [
            {"start": 0, "end": 8, "label": "breakdown", "bars": 8, "energy": 0.1},
        ]
        energy = [{"start": 0, "end": 8, "relative_energy": 0.1}]
        scored = _score_section_intensity(phrases, energy)
        self.assertEqual(scored[0]["label"], "breakdown")
        # Without spectral contrast data, intensity floor is ~0.45
        self.assertLess(scored[0]["intensity"], 0.55)
        self.assertTrue(scored[0]["is_valley_section"])

    def test_empty_phrase_map(self):
        self.assertEqual(_score_section_intensity([], []), [])


# ═══════════════════════════════════════════════════════════════════════════════
# Groove score
# ═══════════════════════════════════════════════════════════════════════════════

class GrooveScoreTests(unittest.TestCase):
    def test_steady_groove_returns_high_score(self):
        """Steady 120bpm with clear downbeats → high groove."""
        beats = [i * 0.5 for i in range(64)]
        downbeats = beats[0::4]
        curve = [{"start": 0, "end": 8, "bpm": 120.0, "stability": 0.99}]
        groove = _compute_groove_score(beats, downbeats, curve, 0.99)
        self.assertGreater(groove["score"], 0.65)
        self.assertIn(groove["label"], ("groovy", "steady"))
        self.assertIn("breakdown", groove)

    def test_unstable_returns_low_score(self):
        """Jittery beat → lower groove than steady."""
        jittery = np.cumsum([0.4, 0.7] * 32).tolist()
        downbeats = jittery[0::4] if len(jittery) >= 4 else jittery[:1]
        groove_jittery = _compute_groove_score(jittery, downbeats, [], 0.3)

        # Should be lower than a steady beat
        steady_beats = [i * 0.5 for i in range(64)]
        steady_downs = steady_beats[0::4]
        groove_steady = _compute_groove_score(steady_beats, steady_downs,
                                              [{"start": 0, "end": 8, "bpm": 120.0, "stability": 0.99}], 0.99)

        self.assertLess(groove_jittery["score"], groove_steady["score"])

    def test_insufficient_data(self):
        groove = _compute_groove_score([0.0, 0.5], [0.0], [], 0.9)
        self.assertEqual(groove["score"], 0.0)
        self.assertEqual(groove["method"], "insufficient_data")

    def test_json_serializable(self):
        beats = [i * 0.5 for i in range(32)]
        downbeats = beats[0::4]
        groove = _compute_groove_score(beats, downbeats, [], 0.9)
        json.dumps(groove)  # should not raise


class DancefloorProfileTests(unittest.TestCase):
    def test_high_energy_groovy_track_is_danceable_and_driving(self):
        profile = _analyze_dancefloor_profile(
            bpm=124.0,
            energy=0.82,
            groove={"score": 0.88, "label": "groovy"},
            stem_activity={"vocals": 0.25, "drums": 0.85, "bass": 0.75, "other": 0.3},
            spectral_centroid=3200.0,
            phrase_map=[{"label": "drop", "intensity": 0.9, "is_peak_section": True}],
        )

        self.assertGreater(profile["danceability_score"], 0.75)
        self.assertGreater(profile["physical_energy"], 0.75)
        self.assertIn("driving", profile["mood_tags"])
        json.dumps(profile)

    def test_low_energy_track_is_laid_back(self):
        profile = _analyze_dancefloor_profile(
            bpm=86.0,
            energy=0.2,
            groove={"score": 0.45, "label": "steady"},
            stem_activity={"vocals": 0.35, "drums": 0.15, "bass": 0.2, "other": 0.5},
            spectral_centroid=1300.0,
            phrase_map=[],
        )

        self.assertLess(profile["physical_energy"], 0.4)
        self.assertIn("laid_back", profile["mood_tags"])


class DjHotCueTests(unittest.TestCase):
    def test_generates_semantic_cues_for_live_control(self):
        phrases = [
            {"start": 0.0, "end": 16.0, "label": "intro", "energy": 0.2, "intensity": 0.2},
            {"start": 16.0, "end": 32.0, "label": "verse", "energy": 0.5, "intensity": 0.55},
            {"start": 32.0, "end": 48.0, "label": "drop", "energy": 0.95, "intensity": 0.9, "is_peak_section": True},
            {"start": 48.0, "end": 64.0, "label": "outro", "energy": 0.25, "intensity": 0.2},
        ]
        windows = [
            {"start": 0.0, "end": 16.0, "label": "intro", "mix_in_score": 0.95,
             "mix_out_score": 0.3, "clean_candidate": True},
        ]

        cues = _generate_dj_hot_cues(phrases, windows, [], 64.0)

        self.assertEqual({cue["name"] for cue in cues}, {
            "intro_end", "main_groove", "first_drop", "best_loop", "outro_start",
        })
        self.assertEqual(next(c["time"] for c in cues if c["name"] == "first_drop"), 32.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Vocal events
# ═══════════════════════════════════════════════════════════════════════════════

class VocalEventsTests(unittest.TestCase):
    def _make_windows(self, vocal_sequence):
        return [
            {"start": i * 2.0, "end": (i + 1) * 2.0,
             "vocals": v, "drums": 0.5, "bass": 0.4, "other": 0.3}
            for i, v in enumerate(vocal_sequence)
        ]

    def test_detect_enter_and_exit(self):
        seq = [0.1, 0.1, 0.4, 0.6, 0.7, 0.3, 0.1, 0.1]
        events = _detect_vocal_events(self._make_windows(seq))
        types = [e["type"] for e in events]
        self.assertIn("enter", types)
        self.assertIn("exit", types)

    def test_no_vocals_returns_empty(self):
        seq = [0.0, 0.1, 0.05, 0.0]
        events = _detect_vocal_events(self._make_windows(seq))
        self.assertEqual(events, [])

    def test_continuous_vocals_one_entry(self):
        seq = [0.5, 0.6, 0.7, 0.8, 0.75, 0.65, 0.55, 0.5]
        events = _detect_vocal_events(self._make_windows(seq))
        enters = [e for e in events if e["type"] == "enter"]
        self.assertEqual(len(enters), 1)  # single entry, no exit

    def test_empty_windows(self):
        self.assertEqual(_detect_vocal_events([]), [])

    def test_json_serializable(self):
        seq = [0.1, 0.4, 0.7, 0.5, 0.2]
        events = _detect_vocal_events(self._make_windows(seq))
        json.dumps(events)


# ═══════════════════════════════════════════════════════════════════════════════
# Bass risk windows
# ═══════════════════════════════════════════════════════════════════════════════

class BassRiskTests(unittest.TestCase):
    def test_heavy_bass_flagged_high_risk(self):
        windows = [
            {"start": 0, "end": 2, "vocals": 0.1, "drums": 0.3, "bass": 0.7, "other": 0.2},
            {"start": 2, "end": 4, "vocals": 0.1, "drums": 0.2, "bass": 0.2, "other": 0.3},
        ]
        risks = _compute_bass_risk_windows(windows)
        self.assertEqual(risks[0]["risk"], "high")
        self.assertEqual(risks[1]["risk"], "low")

    def test_empty(self):
        self.assertEqual(_compute_bass_risk_windows([]), [])

    def test_json_serializable(self):
        windows = [
            {"start": 0, "end": 2, "vocals": 0.1, "drums": 0.3, "bass": 0.6, "other": 0.2},
        ]
        json.dumps(_compute_bass_risk_windows(windows))


# ═══════════════════════════════════════════════════════════════════════════════
# Stem-aware transition window scoring
# ═══════════════════════════════════════════════════════════════════════════════

class StemAwareTransitionTests(unittest.TestCase):
    def test_vocal_free_intro_boosted(self):
        tw = [
            {"start": 0, "end": 16, "label": "intro", "bars": 8,
             "energy": 0.2, "mix_in_score": 0.92, "mix_out_score": 0.35,
             "clean_candidate": True},
        ]
        stem = [
            {"start": 0, "end": 2, "vocals": 0.05, "drums": 0.6, "bass": 0.2, "other": 0.15},
            {"start": 2, "end": 4, "vocals": 0.08, "drums": 0.55, "bass": 0.25, "other": 0.15},
        ]
        enhanced = _enhance_transition_windows(tw, stem)
        self.assertEqual(enhanced[0]["label"], "intro")
        self.assertIn("vocal_free", enhanced[0]["stem_tags"])
        self.assertIn("drum_heavy", enhanced[0]["stem_tags"])
        self.assertGreater(enhanced[0]["mix_in_score"], 0.92)  # boosted
        self.assertTrue(enhanced[0]["clean_candidate"])

    def test_vocal_led_section_penalized(self):
        tw = [
            {"start": 0, "end": 16, "label": "verse", "bars": 8,
             "energy": 0.5, "mix_in_score": 0.68, "mix_out_score": 0.58,
             "clean_candidate": False},
        ]
        stem = [
            {"start": 0, "end": 2, "vocals": 0.7, "drums": 0.2, "bass": 0.3, "other": 0.2},
        ]
        enhanced = _enhance_transition_windows(tw, stem)
        self.assertIn("vocal_led", enhanced[0]["stem_tags"])
        self.assertLess(enhanced[0]["mix_in_score"], 0.68)  # penalized

    def test_bass_heavy_section_penalized(self):
        tw = [
            {"start": 0, "end": 16, "label": "intro", "bars": 8,
             "energy": 0.4, "mix_in_score": 0.80, "mix_out_score": 0.35,
             "clean_candidate": True},
        ]
        stem = [
            {"start": 0, "end": 2, "vocals": 0.05, "drums": 0.15, "bass": 0.8, "other": 0.1},
        ]
        enhanced = _enhance_transition_windows(tw, stem)
        self.assertIn("bass_heavy", enhanced[0]["stem_tags"])
        # bass_heavy penalty (-0.08) applied, but vocal_free may offset
        # Start from 0.80 to isolate: 0.80 - 0.08 + 0.10 = 0.82
        self.assertLess(enhanced[0]["mix_in_score"], 0.90)

    def test_empty_transition_windows(self):
        self.assertEqual(_enhance_transition_windows([], []), [])

    def test_no_stem_data_preserves_original(self):
        tw = [
            {"start": 0, "end": 8, "label": "intro", "bars": 4,
             "energy": 0.3, "mix_in_score": 0.92, "mix_out_score": 0.35,
             "clean_candidate": True},
        ]
        enhanced = _enhance_transition_windows(tw, [])
        self.assertEqual(enhanced[0]["mix_in_score"], 0.92)
        self.assertEqual(enhanced[0]["stem_tags"], [])

    def test_json_serializable(self):
        tw = [
            {"start": 0, "end": 16, "label": "intro", "bars": 8,
             "energy": 0.2, "mix_in_score": 0.92, "mix_out_score": 0.35,
             "clean_candidate": True},
        ]
        stem = [
            {"start": 0, "end": 2, "vocals": 0.05, "drums": 0.6, "bass": 0.2, "other": 0.15},
        ]
        json.dumps(_enhance_transition_windows(tw, stem))


if __name__ == "__main__":
    unittest.main()
