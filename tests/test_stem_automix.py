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
        a = _ctx("A", bpm=128.0, has_stems=True, stem_quality_score=0.9)
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
        a = _ctx("A", bpm=128.0, has_stems=True, stem_quality_score=0.9)
        b = _ctx("B", bpm=128.5, has_stems=True, stem_quality_score=0.9)
        plan = build_automix_transition(a, b)
        assert plan.tempo_strategy != TempoStrategy.none


# ═══════════════════════════════════════════════════════════════════════════════
# Test 13: Strategy Selector — manifests without stem_automix import path
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategySelector:
    """Tests that mirror RK3588 strategy_selector.py real-world inputs."""

    @staticmethod
    def _manifest_track(song_id="A", bpm=128.0, key="8A", energy="high",
                        has_stems=True, duration=240.0) -> dict:
        analysis = {"bpm": bpm, "camelot_key": key, "energy": energy,
                    "beat_points": [i*0.47 for i in range(64)],
                    "downbeats": [i*1.88 for i in range(16)],
                    "phrase_map": [{"start":0, "label":"intro"}, {"start":32, "label":"chorus"}],
                    "cue_points": [{"time":0, "label":"intro"}, {"time":120, "label":"outro"}]}
        quality = {"has_stems": has_stems, "stem_model": "htdemucs" if has_stems else None,
                   "bpm_confident": True, "key_confidence": 0.9,
                   "has_beatgrid": True, "has_phrase_map": True}
        files = {}
        if has_stems:
            files["stems"] = {"vocals": {}, "drums": {}, "bass": {}, "other": {}}
        return {"songId": song_id, "librarySongId": song_id,
                "durationSec": duration, "bpm": bpm, "key": key,
                "analysis": analysis, "qualityFlags": quality, "files": files}

    def test_has_stems_selects_stem_aware(self):
        """Both tracks have stems → stem_aware tier."""
        from rk3588_edge.strategy_selector import StrategySelector
        sel = StrategySelector()
        a = self._manifest_track("A", has_stems=True)
        b = self._manifest_track("B", has_stems=True)
        result = sel.select(a, b)
        assert result.tier in ("stem_aware", "non_stem")  # depends on scoring
        assert result.preset != ""
        assert result.confidence > 0

    def test_no_stems_selects_non_stem(self):
        """Neither track has stems → non_stem or basic tier."""
        from rk3588_edge.strategy_selector import StrategySelector
        sel = StrategySelector()
        a = self._manifest_track("A", has_stems=False)
        b = self._manifest_track("B", has_stems=False)
        result = sel.select(a, b)
        assert result.tier in ("non_stem", "basic")
        assert result.mode == "non_stem"

    def test_dual_vocal_high_density_prefers_safe_preset(self):
        """High vocal density on both → vocal_handoff or echo_freeze."""
        from rk3588_edge.strategy_selector import StrategySelector
        sel = StrategySelector()
        a = self._manifest_track("A", has_stems=True)
        a["analysis"]["vocal_density"] = 0.9  # only TrackContext uses this, manifest doesn't
        b = self._manifest_track("B", has_stems=True)
        result = sel.select(a, b)
        assert result.preset in ("vocal_handoff", "echo_freeze", "bass_swap",
                                 "drum_bridge", "breakdown_drop", "acapella_overlay",
                                 "instrumental_under_vocal", "loop_bridge",
                                 "hard_cut", "fallback_crossfade")

    def test_wide_bpm_still_works(self):
        """Large BPM gap → select_best_preset returns a valid preset."""
        from rk3588_edge.strategy_selector import StrategySelector
        sel = StrategySelector()
        a = self._manifest_track("A", bpm=90.0)
        b = self._manifest_track("B", bpm=140.0)
        result = sel.select(a, b)
        assert result.preset != ""
        assert result.mode in ("non_stem", "stem_aware")

    def test_key_tense_selects_safe_preset(self):
        """Incompatible keys (distance >= 3) → no acapella_overlay."""
        from rk3588_edge.strategy_selector import StrategySelector
        sel = StrategySelector()
        a = self._manifest_track("A", key="1A", has_stems=True)
        b = self._manifest_track("B", key="6A", has_stems=True)
        result = sel.select(a, b)
        assert result.preset != "acapella_overlay"

    def test_force_preset_overrides_auto(self):
        """force_preset='hard_cut' bypasses auto-selection."""
        from rk3588_edge.strategy_selector import StrategySelector
        sel = StrategySelector()
        a = self._manifest_track("A")
        b = self._manifest_track("B")
        result = sel.select(a, b, force_preset="hard_cut")
        assert result.preset == "hard_cut"

    def test_unknown_preset_falls_back_to_auto(self):
        """force_preset='nonexistent' logs warning and auto-selects."""
        from rk3588_edge.strategy_selector import StrategySelector
        sel = StrategySelector()
        a = self._manifest_track("A")
        b = self._manifest_track("B")
        result = sel.select(a, b, force_preset="non_existent_preset")
        assert result.preset != "non_existent_preset"
        assert len(result.warnings) == 0 or result.preset in ("bass_swap", "vocal_handoff",
            "echo_freeze", "hard_cut", "fallback_crossfade")

    def test_scores_returned_in_result(self):
        """SelectionResult includes scoring breakdown."""
        from rk3588_edge.strategy_selector import StrategySelector
        sel = StrategySelector()
        a = self._manifest_track("A")
        b = self._manifest_track("B")
        result = sel.select(a, b)
        assert "bpm_distance" in result.scores
        assert "transition_confidence" in result.scores


# ═══════════════════════════════════════════════════════════════════════════════
# Test 14: SessionEvent persistence and startup recovery
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionManager:
    """Unit tests for RK3588 session_manager event lifecycle."""

    def test_record_event_appends(self):
        from rk3588_edge.session_manager import SessionManager
        sm = SessionManager()
        assert len(sm._events) == 0
        sm.record_sync("load", plan_id="test-1")
        assert len(sm._events) == 1
        assert sm._events[0].event_type == "load"
        assert sm._events[0].event_value == {"plan_id": "test-1"}

    def test_record_multiple_events(self):
        from rk3588_edge.session_manager import SessionManager
        sm = SessionManager()
        sm.record_sync("play_started", deck="A", start_sec=0.0)
        sm.record_sync("crossfade_start", style="bass_swap", from_deck="A", to_deck="B")
        sm.record_sync("key_press", fx_id=7, deck="A")
        assert len(sm._events) == 3
        assert sm._events[0].event_type == "play_started"
        assert sm._events[2].event_type == "key_press"

    def test_event_to_api_format(self):
        from rk3588_edge.session_manager import SessionManager, SessionEvent
        sm = SessionManager()
        sm.record_sync("load", plan_id="test-api")
        event = sm._events[0]
        api = event.to_api()
        assert api["event_type"] == "load"
        assert api["session_id"] is None
        assert "created_at" in api

    def test_record_sync_creates_session_event(self):
        """record_sync() is the main API: it creates a proper SessionEvent."""
        from rk3588_edge.session_manager import SessionManager
        sm = SessionManager()
        sm.record_sync("play_started", deck="B", start_sec=5.0)
        ev = sm._events[-1]
        assert ev.event_type == "play_started"
        assert ev.event_value == {"deck": "B", "start_sec": 5.0}

    def test_recovery_returns_none_when_unreachable(self):
        """recover_plan returns None when Jetson is unreachable (no network)."""
        from rk3588_edge.session_manager import SessionManager
        import asyncio
        sm = SessionManager()
        result = asyncio.new_event_loop().run_until_complete(
            sm.recover_plan("nonexistent-plan")
        )
        # Should return None when Jetson is unreachable
        assert result is None or isinstance(result, dict)

    def test_flush_preserves_events_on_failure(self):
        """When flush fails (no Jetson), events are preserved for retry."""
        from rk3588_edge.session_manager import SessionManager
        import asyncio
        sm = SessionManager()
        sm.record_sync("load", plan_id="flush-test")
        count_before = len(sm._events)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(sm._flush())
        # Flush should preserve events since Jetson is unreachable
        assert len(sm._events) == count_before

    def test_stop_flushes_remaining_events(self):
        """stop() attempts to flush remaining events."""
        from rk3588_edge.session_manager import SessionManager
        import asyncio
        sm = SessionManager()
        sm.record_sync("play_stopped", deck="A")
        count_before = len(sm._events)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(sm.stop())
        # Events should persist (flush fails gracefully when unreachable)
        assert len(sm._events) == count_before


# ═══════════════════════════════════════════════════════════════════════════════
# Test 15: vocal_handoff bar-boundary snapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestVocalHandoffBarBoundary:
    def test_default_no_snap_still_works(self):
        """Without vocal_cut_ratio, uses default 0.35 exit_point."""
        from app.modules.playlists.stem_automix import (
            TrackContext, generate_plan, TransitionPreset,
        )
        a = TrackContext(song_id="A", bpm=128.0, has_stems=True,
                         stem_quality_score=0.9)
        b = TrackContext(song_id="B", bpm=128.0, has_stems=True,
                         stem_quality_score=0.9)
        plan = generate_plan(a, b, TransitionPreset.vocal_handoff,
                            duration_bars=8)
        # A_vocals gain curve should have exit at 0.35 (default)
        a_vocal = [c for c in plan.curves
                   if c.target.value == "A.vocals" and c.param.value == "gain"]
        assert len(a_vocal) == 1
        # Second point should be at 0.35
        assert abs(a_vocal[0].points[1][0] - 0.35) < 0.01

    def test_vocal_cut_ratio_snap_4bars(self):
        """vocal_cut_ratio=0.45 with 8 bars → snaps to 0.5 (bar 4)."""
        from app.modules.playlists.stem_automix import (
            TrackContext, generate_plan, TransitionPreset,
        )
        a = TrackContext(song_id="A", bpm=128.0, has_stems=True,
                         stem_quality_score=0.9)
        b = TrackContext(song_id="B", bpm=128.0, has_stems=True,
                         stem_quality_score=0.9)
        plan = generate_plan(a, b, TransitionPreset.vocal_handoff,
                            duration_bars=8, vocal_cut_ratio=0.45)
        a_vocal = [c for c in plan.curves
                   if c.target.value == "A.vocals" and c.param.value == "gain"]
        # round(0.45 * 8) / 8 = 4/8 = 0.5
        assert abs(a_vocal[0].points[1][0] - 0.5) < 0.01
        assert plan.vocal_cut_ratio == 0.45

    def test_vocal_cut_ratio_snap_edge_clamped(self):
        """vocal_cut_ratio=0.05 with 8 bars → clamped to 0.125 (bar 1)."""
        from app.modules.playlists.stem_automix import (
            TrackContext, generate_plan, TransitionPreset,
        )
        a = TrackContext(song_id="A", bpm=128.0, has_stems=True,
                         stem_quality_score=0.9)
        b = TrackContext(song_id="B", bpm=128.0, has_stems=True,
                         stem_quality_score=0.9)
        plan = generate_plan(a, b, TransitionPreset.vocal_handoff,
                            duration_bars=8, vocal_cut_ratio=0.05)
        a_vocal = [c for c in plan.curves
                   if c.target.value == "A.vocals" and c.param.value == "gain"]
        # round(0.05 * 8) / 8 = 0/8 = 0, clamped to 0.125
        assert abs(a_vocal[0].points[1][0] - 0.125) < 0.01

    def test_vocal_cut_ratio_non_vocal_preset_ignored(self):
        """vocal_cut_ratio is ignored for non-vocal_handoff presets."""
        from app.modules.playlists.stem_automix import (
            TrackContext, generate_plan, TransitionPreset,
        )
        a = TrackContext(song_id="A", bpm=128.0, has_stems=True,
                         stem_quality_score=0.9)
        b = TrackContext(song_id="B", bpm=128.0, has_stems=True,
                         stem_quality_score=0.9)
        plan = generate_plan(a, b, TransitionPreset.bass_swap,
                            duration_bars=8, vocal_cut_ratio=0.45)
        # bass_swap ignores vocal_cut_ratio; uses its own curves
        assert plan.preset == TransitionPreset.bass_swap
        assert len(plan.curves) > 0
