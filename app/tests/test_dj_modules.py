"""
Tests for upgraded DJ modules (Module 4 & 5):
  - dj_transition: 50Hz automation, real EQ/reverb/delay curves
  - dj_sequencer: structure-aware transitions, gradual BPM, style suggestion
  - audio_processor: DSP chain config, time-stretch, stem mix
"""
import unittest
import math

from app.modules.music.dj_transition import (
    TransitionAutomation,
    TRANSITION_STYLES,
    generate_transition_automation,
)
from app.modules.music.dj_sequencer import (
    DJTrack,
    TransitionPlan,
    ENERGY_PROFILES,
    HARMONIC_WEIGHTS,
    harmonize,
    compute_transition_params,
    score_pair,
    build_dj_set,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_track(song_id: int, bpm: float = 120.0, key: str = "8A",
                energy: float = 0.5, dur: float = 200.0,
                phrase_map: list | None = None) -> DJTrack:
    bar_sec = 4 * 60.0 / bpm
    num_downbeats = int(dur / bar_sec) + 1
    return DJTrack(
        song_id=song_id, title=f"Track {song_id}", artist="Test",
        bpm=bpm, camelot_key=key, energy=energy, duration=dur,
        downbeats=[i * bar_sec for i in range(num_downbeats)],
        phrase_map=phrase_map or [],
    )


# ════════════════════════════════════════════════════════════════════════════
#  DJ Transition Tests
# ════════════════════════════════════════════════════════════════════════════

class TestTransitionAutomation(unittest.TestCase):
    """Test TransitionAutomation dataclass defaults."""

    def test_default_sample_rate_50hz(self):
        auto = TransitionAutomation(total_duration_sec=8.0)
        self.assertEqual(auto.sample_rate, 50.0)

    def test_has_filter_frequency_fields(self):
        auto = TransitionAutomation(total_duration_sec=8.0)
        self.assertIsInstance(auto.a_highpass_hz, list)
        self.assertIsInstance(auto.a_lowpass_hz, list)
        self.assertIsInstance(auto.b_highpass_hz, list)
        self.assertIsInstance(auto.b_lowpass_hz, list)

    def test_has_reverb_delay_fields(self):
        auto = TransitionAutomation(total_duration_sec=8.0)
        self.assertIsInstance(auto.a_reverb, list)
        self.assertIsInstance(auto.a_delay, list)

    def test_no_legacy_echo_field(self):
        auto = TransitionAutomation(total_duration_sec=8.0)
        self.assertFalse(hasattr(auto, "a_echo"))


class TestTransitionGeneration(unittest.TestCase):
    """Test all 7 transition presets produce correct output."""

    def test_all_styles_exist(self):
        expected = ["smooth", "power", "bass_swap", "echo_out", "filter", "cut", "slam"]
        self.assertEqual(TRANSITION_STYLES, expected)

    def test_all_styles_generate_valid_output(self):
        for style in TRANSITION_STYLES:
            with self.subTest(style=style):
                auto = generate_transition_automation(
                    overlap_sec=8.0, overlap_bars=8, bpm=120.0, style=style,
                )
                n = int(8.0 * 50.0)  # 50Hz * 8s = 400 samples

                # Stem gain arrays correct length
                self.assertEqual(len(auto.a_drums), n, f"{style}: a_drums")
                self.assertEqual(len(auto.b_drums), n, f"{style}: b_drums")
                self.assertEqual(len(auto.a_volume), n, f"{style}: a_volume")
                self.assertEqual(len(auto.b_volume), n, f"{style}: b_volume")

                # FX arrays correct length
                self.assertEqual(len(auto.a_highpass_hz), n, f"{style}: a_highpass_hz")
                self.assertEqual(len(auto.a_lowpass_hz), n, f"{style}: a_lowpass_hz")
                self.assertEqual(len(auto.b_highpass_hz), n, f"{style}: b_highpass_hz")
                self.assertEqual(len(auto.b_lowpass_hz), n, f"{style}: b_lowpass_hz")
                self.assertEqual(len(auto.a_reverb), n, f"{style}: a_reverb")
                self.assertEqual(len(auto.a_delay), n, f"{style}: a_delay")

    def test_gain_values_in_range(self):
        for style in TRANSITION_STYLES:
            with self.subTest(style=style):
                auto = generate_transition_automation(
                    overlap_sec=4.0, overlap_bars=4, bpm=128.0, style=style,
                )
                for name in ["a_drums", "a_bass", "a_vocals", "a_other",
                             "b_drums", "b_bass", "b_vocals", "b_other",
                             "a_volume", "b_volume", "a_reverb", "a_delay"]:
                    values = getattr(auto, name)
                    self.assertTrue(all(0.0 <= v <= 1.0 for v in values),
                                    f"{style}.{name} out of [0,1]")

    def test_filter_frequencies_valid(self):
        for style in TRANSITION_STYLES:
            with self.subTest(style=style):
                auto = generate_transition_automation(
                    overlap_sec=4.0, overlap_bars=4, bpm=128.0, style=style,
                )
                for name in ["a_highpass_hz", "a_lowpass_hz",
                             "b_highpass_hz", "b_lowpass_hz"]:
                    values = getattr(auto, name)
                    self.assertTrue(all(15.0 <= v <= 25000.0 for v in values),
                                    f"{style}.{name} freq out of range")

    def test_50hz_resolution(self):
        auto = generate_transition_automation(
            overlap_sec=8.0, overlap_bars=8, bpm=120.0, style="smooth",
        )
        self.assertEqual(auto.sample_rate, 50.0)
        self.assertEqual(len(auto.a_drums), 400)  # 8s * 50Hz

    def test_smooth_crossfade_pattern(self):
        """Smooth: A bass exits first, A drums last."""
        auto = generate_transition_automation(
            overlap_sec=8.0, overlap_bars=8, bpm=120.0, style="smooth",
        )
        # At 25% progress, A bass should be lower than A drums
        idx_25 = 100  # 25% of 400
        self.assertLess(auto.a_bass[idx_25], auto.a_drums[idx_25])

    def test_filter_has_real_frequency_sweep(self):
        """Filter preset should sweep highpass from ~20Hz upward."""
        auto = generate_transition_automation(
            overlap_sec=8.0, overlap_bars=8, bpm=120.0, style="filter",
        )
        # First sample: highpass near 20Hz
        self.assertAlmostEqual(auto.a_highpass_hz[0], 20.0, delta=5.0)
        # Last sample: highpass near 5000Hz
        self.assertGreater(auto.a_highpass_hz[-1], 4000.0)
        # B lowpass opening: last sample near 20000Hz
        self.assertGreater(auto.b_lowpass_hz[-1], 19000.0)

    def test_echo_out_has_real_reverb(self):
        """Echo_out preset should ramp up reverb on A."""
        auto = generate_transition_automation(
            overlap_sec=8.0, overlap_bars=8, bpm=120.0, style="echo_out",
        )
        self.assertAlmostEqual(auto.a_reverb[0], 0.0, delta=0.05)
        self.assertGreater(auto.a_reverb[-1], 0.5)
        self.assertGreater(auto.a_delay[-1], 0.3)

    def test_slam_has_highpass_tension(self):
        """Slam preset should sweep highpass during tension build."""
        auto = generate_transition_automation(
            overlap_sec=8.0, overlap_bars=8, bpm=120.0, style="slam",
        )
        # First sample: near bypass (20Hz)
        self.assertAlmostEqual(auto.a_highpass_hz[0], 20.0, delta=5.0)
        # At 35% (before drop): highpass should be elevated
        idx_35 = int(400 * 0.35)
        self.assertGreater(auto.a_highpass_hz[idx_35], 500.0)

    def test_power_equal_power_law(self):
        """Power: cos/sin equal-power crossfade."""
        auto = generate_transition_automation(
            overlap_sec=4.0, overlap_bars=4, bpm=128.0, style="power",
        )
        n = len(auto.a_volume)
        mid = n // 2
        a = auto.a_volume[mid]
        b = auto.b_volume[mid]
        # At midpoint, a² + b² ≈ 1 (equal power)
        power_sum = a ** 2 + b ** 2
        self.assertAlmostEqual(power_sum, 1.0, delta=0.05)

    def test_zero_overlap_defaults_to_8sec(self):
        auto = generate_transition_automation(
            overlap_sec=0, overlap_bars=0, bpm=120.0, style="smooth",
        )
        self.assertEqual(auto.total_duration_sec, 8.0)
        self.assertEqual(len(auto.a_drums), 400)


# ════════════════════════════════════════════════════════════════════════════
#  DJ Sequencer Tests
# ════════════════════════════════════════════════════════════════════════════

class TestScorePair(unittest.TestCase):
    """Test pairwise scoring function."""

    def test_perfect_match(self):
        a = _make_track(1, bpm=120, key="8A", energy=0.5)
        b = _make_track(2, bpm=120, key="8A", energy=0.5)
        plan = score_pair(a, b)
        self.assertGreaterEqual(plan.score, 90)

    def test_bad_match(self):
        a = _make_track(1, bpm=90, key="1A", energy=0.2)
        b = _make_track(2, bpm=160, key="7B", energy=0.9)
        plan = score_pair(a, b)
        self.assertLess(plan.score, 30)

    def test_halftime_bpm_recognized(self):
        a = _make_track(1, bpm=120, key="8A")
        b = _make_track(2, bpm=60, key="8A")
        plan = score_pair(a, b)
        self.assertGreater(plan.bpm_score, 50)


class TestHarmonize(unittest.TestCase):
    """Test the harmonize ordering engine."""

    def test_basic_ordering(self):
        tracks = [
            _make_track(1, bpm=120, key="8A", energy=0.3),
            _make_track(2, bpm=122, key="9A", energy=0.5),
            _make_track(3, bpm=124, key="10A", energy=0.7),
        ]
        ordered, transitions = harmonize(tracks, energy_profile="warmup")
        self.assertEqual(len(ordered), 3)
        self.assertEqual(len(transitions), 2)

    def test_single_track(self):
        tracks = [_make_track(1)]
        ordered, transitions = harmonize(tracks)
        self.assertEqual(len(ordered), 1)
        self.assertEqual(len(transitions), 0)

    def test_start_song_locked(self):
        tracks = [
            _make_track(1, bpm=120, key="8A"),
            _make_track(2, bpm=122, key="9A"),
            _make_track(3, bpm=124, key="10A"),
        ]
        ordered, _ = harmonize(tracks, start_song_id=3)
        self.assertEqual(ordered[0].song_id, 3)


class TestTransitionPlan(unittest.TestCase):
    """Test TransitionPlan new fields."""

    def test_has_gradual_bpm_fields(self):
        plan = TransitionPlan(
            from_song_id=1, to_song_id=2,
            score=80, bpm_score=90, key_score=80, energy_score=70,
        )
        self.assertEqual(plan.bpm_a_target, 0.0)
        self.assertEqual(plan.bpm_b_target, 0.0)
        self.assertEqual(plan.suggested_style, "smooth")
        self.assertEqual(plan.a_section_out, "")
        self.assertEqual(plan.b_section_in, "")


class TestComputeTransitionParams(unittest.TestCase):
    """Test structure-aware transition parameter computation."""

    def test_basic_overlap(self):
        a = _make_track(1, bpm=120, dur=240.0)
        b = _make_track(2, bpm=120, dur=220.0)
        plan = score_pair(a, b)
        plan = compute_transition_params(a, b, plan, overlap_bars=8)
        self.assertGreater(plan.overlap_sec, 0)
        self.assertGreater(plan.mix_start_time, 0)

    def test_gradual_bpm_small_diff(self):
        """Small BPM difference: both adjust to midpoint."""
        a = _make_track(1, bpm=120)
        b = _make_track(2, bpm=124)
        plan = score_pair(a, b)
        plan = compute_transition_params(a, b, plan)
        self.assertAlmostEqual(plan.bpm_a_target, 122.0, delta=0.1)
        self.assertAlmostEqual(plan.bpm_b_target, 122.0, delta=0.1)

    def test_gradual_bpm_large_diff(self):
        """Large BPM difference: B adjusts to A."""
        a = _make_track(1, bpm=120)
        b = _make_track(2, bpm=140)
        plan = score_pair(a, b)
        plan = compute_transition_params(a, b, plan)
        self.assertAlmostEqual(plan.bpm_a_target, 120.0, delta=0.1)
        self.assertAlmostEqual(plan.bpm_b_target, 120.0, delta=0.1)

    def test_structure_aware_outro(self):
        """When phrase_map has 'outro', mix-out should start there."""
        phrase_map = [
            {"start": 0, "end": 30, "bars": 8, "label": "intro"},
            {"start": 30, "end": 150, "bars": 32, "label": "verse"},
            {"start": 150, "end": 200, "bars": 16, "label": "outro"},
        ]
        a = _make_track(1, bpm=120, dur=200.0, phrase_map=phrase_map)
        b = _make_track(2, bpm=120, dur=200.0)
        plan = score_pair(a, b)
        plan = compute_transition_params(a, b, plan)
        # Mix should start at/near the outro
        self.assertGreaterEqual(plan.mix_start_time, 140.0)
        self.assertEqual(plan.a_section_out, "outro")

    def test_suggested_style_slam_on_energy_jump(self):
        a = _make_track(1, bpm=120, key="8A", energy=0.3)
        b = _make_track(2, bpm=122, key="8A", energy=0.8)
        plan = score_pair(a, b)
        plan = compute_transition_params(a, b, plan)
        self.assertEqual(plan.suggested_style, "slam")

    def test_suggested_style_echo_on_energy_drop(self):
        a = _make_track(1, bpm=120, key="8A", energy=0.8)
        b = _make_track(2, bpm=122, key="8A", energy=0.4)
        plan = score_pair(a, b)
        plan = compute_transition_params(a, b, plan)
        self.assertEqual(plan.suggested_style, "echo_out")

    def test_suggested_style_smooth_on_same_key(self):
        a = _make_track(1, bpm=120, key="8A", energy=0.5)
        b = _make_track(2, bpm=122, key="8A", energy=0.6)
        plan = score_pair(a, b)
        plan = compute_transition_params(a, b, plan)
        self.assertEqual(plan.suggested_style, "smooth")


class TestBuildDJSet(unittest.TestCase):
    """Test full DJ set pipeline."""

    def test_full_pipeline(self):
        tracks = [
            _make_track(1, bpm=120, key="8A", energy=0.3, dur=200),
            _make_track(2, bpm=122, key="9A", energy=0.5, dur=180),
            _make_track(3, bpm=124, key="10A", energy=0.7, dur=220),
            _make_track(4, bpm=126, key="11A", energy=0.9, dur=210),
        ]
        ordered, transitions = build_dj_set(
            tracks, energy_profile="warmup", harmonic_weight="balanced",
        )
        self.assertEqual(len(ordered), 4)
        self.assertEqual(len(transitions), 3)

        for t in transitions:
            self.assertGreater(t.overlap_sec, 0)
            self.assertIn(t.suggested_style, TRANSITION_STYLES)
            self.assertGreater(t.bpm_a_target, 0)
            self.assertGreater(t.bpm_b_target, 0)


# ════════════════════════════════════════════════════════════════════════════
#  Audio Processor Config Tests (no heavy deps needed)
# ════════════════════════════════════════════════════════════════════════════

class TestAudioProcessorConfig(unittest.TestCase):
    """Test audio_processor constants and style configs (no audio libs needed)."""

    def test_style_target_bpm(self):
        from app.modules.music.audio_processor import STYLE_TARGET_BPM
        self.assertEqual(len(STYLE_TARGET_BPM), 7)
        self.assertEqual(STYLE_TARGET_BPM["breaking"], 128)
        self.assertEqual(STYLE_TARGET_BPM["hiphop"], 92)

    def test_style_stem_mix(self):
        from app.modules.music.audio_processor import STYLE_STEM_MIX
        for style, gains in STYLE_STEM_MIX.items():
            self.assertEqual(len(gains), 4, f"{style} should have 4 gain values")
            for g in gains:
                self.assertGreater(g, 0.0, f"{style} gain should be positive")

    def test_pipeline_name_updated(self):
        """Verify pipeline string references upgraded components."""
        import ast
        import inspect
        from app.modules.music import audio_processor
        source = inspect.getsource(audio_processor)
        self.assertIn("htdemucs_ft", source)
        self.assertIn("rubberband", source)
        self.assertIn("pedalboard_pro", source)


if __name__ == "__main__":
    unittest.main()
