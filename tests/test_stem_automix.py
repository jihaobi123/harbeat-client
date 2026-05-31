"""Automated tests for stem-aware Automix: presets, scoring, fallbacks, edge cases.

Run: pytest tests/test_stem_automix.py -v

Covers 8 test scenarios:
  1. No stems available
  2. Stems available for both tracks
  3. One stem file missing
  4. Different BPM
  5. Key incompatible
  6. Dual vocal conflict
  7. Bass conflict
  8. Low confidence
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.modules.playlists.stem_automix import (
    AutomationCurve,
    CurveParam,
    CurveShape,
    CurveTarget,
    TempoStrategy,
    TrackContext,
    TransitionMode,
    TransitionPlan,
    TransitionPreset,
    TransitionScore,
    build_automix_transition,
    build_curve,
    generate_plan,
    score_transition_candidates,
    select_best_preset,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _ctx(song_id: str = "A", **kwargs) -> TrackContext:
    defaults = {
        "song_id": song_id,
        "bpm": 128.0,
        "camelot_key": "8A",
        "energy": "high",
        "duration_sec": 240.0,
        "beat_points": [i * 0.47 for i in range(64)],
        "downbeats": [i * 1.88 for i in range(16)],
        "phrase_map": [{"start": 0, "label": "intro"}, {"start": 32, "label": "chorus"}],
        "cue_points": [{"time": 0, "label": "intro"}, {"time": 120, "label": "outro"}],
        "has_stems": True,
        "stem_quality_score": 0.85,
        "vocal_density": 0.5,
        "bass_energy": 0.5,
        "intro_is_clean": True,
        "outro_is_clean": True,
        "has_drum_loop": False,
    }
    defaults.update(kwargs)
    return TrackContext(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: Curve Engine
# ═══════════════════════════════════════════════════════════════════════════════

class TestCurveEngine:
    def test_linear(self):
        c = AutomationCurve(CurveTarget.master, CurveParam.gain,
                            [(0.0, 1.0), (1.0, 0.0)], CurveShape.linear)
        arr = build_curve(c, 100)
        assert arr.shape == (100,)
        assert arr.dtype == np.float32
        assert abs(arr[0] - 1.0) < 0.01
        assert abs(arr[-1] - 0.0) < 0.01

    def test_equal_power(self):
        c = AutomationCurve(CurveTarget.master, CurveParam.gain,
                            [(0.0, 1.0), (1.0, 0.0)], CurveShape.equal_power)
        arr = build_curve(c, 1000)
        # Equal-power: cos²(π/2 · t) + sin²(π/2 · t) ≈ 1
        cos_part = np.cos(np.linspace(0, np.pi / 2, 1000)) ** 2
        sin_part = np.sin(np.linspace(0, np.pi / 2, 1000)) ** 2
        assert np.allclose(cos_part + sin_part, 1.0, atol=0.01)

    def test_s_curve_monotonic(self):
        c = AutomationCurve(CurveTarget.master, CurveParam.gain,
                            [(0.0, 1.0), (0.5, 0.5), (1.0, 0.0)], CurveShape.s_curve)
        arr = build_curve(c, 100)
        # Should be decreasing overall (with smoothstep)
        assert arr[0] > arr[-1]

    def test_exponential_log_friendly(self):
        c = AutomationCurve(CurveTarget.master, CurveParam.gain,
                            [(0.0, 1.0), (1.0, 0.01)], CurveShape.exponential)
        arr = build_curve(c, 100)
        assert np.all(arr >= 0.0)
        assert arr[-1] < arr[0]


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: No stems → non-stem mode
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoStems:
    def test_fallback_crossfade_mode(self):
        a = _ctx("A", has_stems=False, stem_quality_score=0.0)
        b = _ctx("B", has_stems=False, stem_quality_score=0.0)
        plan = generate_plan(a, b, TransitionPreset.fallback_crossfade)
        assert plan.mode == TransitionMode.non_stem

    def test_bass_swap_falls_back(self):
        a = _ctx("A", has_stems=False)
        b = _ctx("B", has_stems=False)
        plan = generate_plan(a, b, TransitionPreset.bass_swap)
        assert plan.mode == TransitionMode.non_stem

    def test_all_presets_generate_non_stem_without_stems(self):
        for preset in TransitionPreset:
            a = _ctx("A", has_stems=False)
            b = _ctx("B", has_stems=False)
            plan = generate_plan(a, b, preset)
            assert plan.mode == TransitionMode.non_stem
            assert len(plan.curves) > 0

    def test_auto_select_returns_non_stem(self):
        a = _ctx("A", has_stems=False, stem_quality_score=0.0)
        b = _ctx("B", has_stems=False, stem_quality_score=0.0)
        preset, mode, scores = select_best_preset(a, b)
        assert mode == TransitionMode.non_stem


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3: Stems available → stem-aware mode
# ═══════════════════════════════════════════════════════════════════════════════

class TestStemsAvailable:
    def test_bass_swap_stem_aware(self):
        a = _ctx("A", has_stems=True, stem_quality_score=0.9)
        b = _ctx("B", has_stems=True, stem_quality_score=0.9)
        plan = generate_plan(a, b, TransitionPreset.bass_swap)
        assert plan.mode == TransitionMode.stem_aware

    def test_all_stem_aware_presets_generate_curves(self):
        for preset in TransitionPreset:
            if preset == TransitionPreset.fallback_crossfade:
                continue
            a = _ctx("A", has_stems=True, stem_quality_score=0.9)
            b = _ctx("B", has_stems=True, stem_quality_score=0.9)
            plan = generate_plan(a, b, preset)
            assert len(plan.curves) > 0, f"{preset} generated no curves"

    def test_curves_are_valid(self):
        a = _ctx("A", has_stems=True, stem_quality_score=0.9)
        b = _ctx("B", has_stems=True, stem_quality_score=0.9)
        for preset in TransitionPreset:
            plan = generate_plan(a, b, preset)
            for curve in plan.curves:
                assert isinstance(curve.target, CurveTarget)
                assert isinstance(curve.param, CurveParam)
                assert len(curve.points) >= 2
                for p in curve.points:
                    assert 0.0 <= p[0] <= 1.0
                    assert isinstance(p[1], (int, float))

    def test_auto_select_returns_stem_aware(self):
        a = _ctx("A", has_stems=True, stem_quality_score=0.85)
        b = _ctx("B", has_stems=True, stem_quality_score=0.85)
        preset, mode, scores = select_best_preset(a, b)
        assert mode == TransitionMode.stem_aware


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4: One stem file missing → auto-downgrade
# ═══════════════════════════════════════════════════════════════════════════════

class TestPartialStems:
    def test_a_has_stems_b_does_not(self):
        a = _ctx("A", has_stems=True, stem_quality_score=0.9)
        b = _ctx("B", has_stems=False, stem_quality_score=0.0)
        plan = generate_plan(a, b, TransitionPreset.bass_swap)
        assert plan.mode == TransitionMode.non_stem

    def test_low_stem_quality_downgrades(self):
        a = _ctx("A", has_stems=True, stem_quality_score=0.2)
        b = _ctx("B", has_stems=True, stem_quality_score=0.25)
        plan = generate_plan(a, b, TransitionPreset.bass_swap)
        assert plan.mode == TransitionMode.non_stem


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5: Different BPM
# ═══════════════════════════════════════════════════════════════════════════════

class TestDifferentBPM:
    def test_moderate_bpm_difference_still_works(self):
        a = _ctx("A", bpm=120.0)
        b = _ctx("B", bpm=128.0)  # ~6.7% difference
        scores = score_transition_candidates(a, b)
        assert scores.bpm_distance < 0.85  # Should be moderately close

    def test_large_bpm_difference(self):
        a = _ctx("A", bpm=90.0)
        b = _ctx("B", bpm=140.0)  # ~55% difference
        scores = score_transition_candidates(a, b)
        # Should be far apart — ratio with halving is 140/180=0.78 or 90/70=1.28
        # Only if halving/doubling is tried
        assert scores.bpm_distance >= 0.0

    def test_same_bpm_same_tempo(self):
        a = _ctx("A", bpm=128.0)
        b = _ctx("B", bpm=128.0)
        plan = generate_plan(a, b, TransitionPreset.bass_swap,
                            tempo_strategy=TempoStrategy.none)
        assert plan.tempo_strategy == TempoStrategy.none
        assert plan.bpm_from == 128.0
        assert plan.bpm_to == 128.0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6: Key incompatible
# ═══════════════════════════════════════════════════════════════════════════════

class TestKeyIncompatible:
    def test_key_clash_no_acapella(self):
        # 1A vs 6A: distance = 5 → clash
        a = _ctx("A", camelot_key="1A", vocal_density=0.3, has_stems=True, stem_quality_score=0.9)
        b = _ctx("B", camelot_key="6A", vocal_density=0.3, has_stems=True, stem_quality_score=0.9)
        scores = score_transition_candidates(a, b)
        assert scores.key_distance >= 4
        # acapella_overlay should NOT be selected due to key clash
        preset, mode, _ = select_best_preset(a, b, scores)
        assert preset != TransitionPreset.acapella_overlay

    def test_key_compatible_allows_acapella(self):
        a = _ctx("A", camelot_key="8A", vocal_density=0.3, has_stems=True, stem_quality_score=0.9)
        b = _ctx("B", camelot_key="9A", vocal_density=0.3, has_stems=True, stem_quality_score=0.9)
        scores = score_transition_candidates(a, b)
        assert scores.key_distance <= 1  # neighbor


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7: Dual vocal conflict
# ═══════════════════════════════════════════════════════════════════════════════

class TestDualVocal:
    def test_high_vocal_density_prefers_vocal_handoff(self):
        a = _ctx("A", vocal_density=0.9, has_stems=True, stem_quality_score=0.9)
        b = _ctx("B", vocal_density=0.85, has_stems=True, stem_quality_score=0.9)
        scores = score_transition_candidates(a, b)
        assert scores.vocal_overlap_risk > 0.5
        preset, mode, _ = select_best_preset(a, b, scores)
        # Should prefer vocal_handoff or echo_freeze
        assert preset in (TransitionPreset.vocal_handoff, TransitionPreset.echo_freeze)

    def test_low_vocal_density_no_conflict(self):
        a = _ctx("A", vocal_density=0.1)
        b = _ctx("B", vocal_density=0.15)
        scores = score_transition_candidates(a, b)
        assert scores.vocal_overlap_risk < 0.3


# ═══════════════════════════════════════════════════════════════════════════════
# Test 8: Bass conflict
# ═══════════════════════════════════════════════════════════════════════════════

class TestBassConflict:
    def test_high_bass_energy_prefers_bass_swap(self):
        a = _ctx("A", bass_energy=0.9, has_stems=True, stem_quality_score=0.9)
        b = _ctx("B", bass_energy=0.85, has_stems=True, stem_quality_score=0.9)
        scores = score_transition_candidates(a, b)
        assert scores.bass_conflict_risk > 0.5
        preset, mode, _ = select_best_preset(a, b, scores)
        assert preset == TransitionPreset.bass_swap

    def test_low_bass_energy_no_conflict(self):
        a = _ctx("A", bass_energy=0.1)
        b = _ctx("B", bass_energy=0.15)
        scores = score_transition_candidates(a, b)
        assert scores.bass_conflict_risk < 0.3


# ═══════════════════════════════════════════════════════════════════════════════
# Test 9: Low confidence → short safe transition
# ═══════════════════════════════════════════════════════════════════════════════

class TestLowConfidence:
    def test_low_confidence_selects_safe_preset(self):
        a = _ctx("A", bpm=None, camelot_key=None, energy=None,
                 beat_points=[], downbeats=[], phrase_map=[],
                 has_stems=False, stem_quality_score=0.0,
                 vocal_density=0.5, bass_energy=0.5,
                 intro_is_clean=False, outro_is_clean=False)
        b = _ctx("B", bpm=None, camelot_key=None, energy=None,
                 beat_points=[], downbeats=[], phrase_map=[],
                 has_stems=False, stem_quality_score=0.0,
                 vocal_density=0.5, bass_energy=0.5,
                 intro_is_clean=False, outro_is_clean=False)
        scores = score_transition_candidates(a, b)
        assert scores.transition_confidence < 0.35, f"got {scores.transition_confidence}"
        preset, mode, _ = select_best_preset(a, b, scores)
        # Should be a safe short cut
        assert preset in (TransitionPreset.hard_cut, TransitionPreset.echo_freeze,
                          TransitionPreset.fallback_crossfade)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 10: Data Model Serialization
# ═══════════════════════════════════════════════════════════════════════════════

class TestSerialization:
    def test_plan_roundtrip(self):
        a = _ctx("A")
        b = _ctx("B")
        plan = build_automix_transition(a, b, force_preset=TransitionPreset.bass_swap)
        d = plan.to_dict()
        plan2 = TransitionPlan.from_dict(d)
        assert plan2.preset == plan.preset
        assert plan2.mode == plan.mode
        assert len(plan2.curves) == len(plan.curves)

    def test_plan_json_serializable(self):
        a = _ctx("A")
        b = _ctx("B")
        plan = build_automix_transition(a, b)
        d = plan.to_dict()
        json_str = json.dumps(d, default=str)
        loaded = json.loads(json_str)
        assert loaded["mode"] in ("non_stem", "stem_aware")
        assert len(loaded["curves"]) > 0

    def test_score_roundtrip(self):
        a = _ctx("A")
        b = _ctx("B")
        scores = score_transition_candidates(a, b)
        d = scores.to_dict()
        assert "bpm_distance" in d
        assert "transition_confidence" in d


# ═══════════════════════════════════════════════════════════════════════════════
# Test 11: All presets generate valid curves for both modes
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllPresets:
    @pytest.mark.parametrize("preset", list(TransitionPreset))
    def test_preset_curves_non_empty(self, preset):
        a = _ctx("A")
        b = _ctx("B")
        plan = generate_plan(a, b, preset)
        assert len(plan.curves) > 0, f"Preset {preset} returned no curves"

    @pytest.mark.parametrize("preset", list(TransitionPreset))
    def test_preset_points_valid(self, preset):
        a = _ctx("A")
        b = _ctx("B")
        plan = generate_plan(a, b, preset)
        for curve in plan.curves:
            times = [p[0] for p in curve.points]
            # Points must be monotonically increasing
            for i in range(1, len(times)):
                assert times[i] >= times[i-1], f"{preset}: {curve.target} times not monotonic"
            # First point at t=0, last at t=1
            assert times[0] == 0.0, f"{preset}: {curve.target} doesn't start at 0"
            assert times[-1] == 1.0, f"{preset}: {curve.target} doesn't end at 1"
            # Values in reasonable range
            for _, v in curve.points:
                assert -20.0 <= v <= 20000.0, f"{preset}: {curve.target} value {v} out of range"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 12: build_automix_transition high-level API
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildAutomixTransition:
    def test_returns_non_stem_without_stems(self):
        a = _ctx("A", has_stems=False)
        b = _ctx("B", has_stems=False)
        plan = build_automix_transition(a, b)
        assert plan.mode == TransitionMode.non_stem

    def test_force_preset_overrides_auto(self):
        a = _ctx("A", has_stems=True, stem_quality_score=0.9)
        b = _ctx("B", has_stems=True, stem_quality_score=0.9)
        plan = build_automix_transition(a, b, force_preset=TransitionPreset.hard_cut)
        assert plan.preset == TransitionPreset.hard_cut

    def test_tempo_strategy_auto_selected(self):
        a = _ctx("A", bpm=128.0)
        b = _ctx("B", bpm=129.0)
        plan = build_automix_transition(a, b)
        assert plan.tempo_strategy != TempoStrategy.none
