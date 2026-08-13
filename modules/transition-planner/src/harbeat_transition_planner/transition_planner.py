"""Default transition planner.

This module ports the current offline default-mix strategy into a fast runtime
planner.  It prefers persisted stem/beat analysis when present and falls back
to beat/bar metadata from MP3 analysis.  It can also wrap the default metadata
inside a section_match-compatible EQ plan for phase-0 mobile compatibility.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from . import eq_transition_strategy
from .band_analysis import band_density, clamp01, curve_average
from .feature_analyzer import FeatureAnalyzer
from .strategy_selector import StrategySelector
from .section_features import vocal_density_in_range


PLANNER_VERSION = "default_mix_planner_v4_shared_fast_cut_window"
REQUIRED_AUDIO_FEATURE_SOURCE = "dj_structure_precomputed_window_v2"
REQUIRED_RENDERER_VERSION = "three_band_default_v9_fast_phase_window"
FAST_CUT_PLANNER_VERSION = "default_mix_planner_v3_precomputed_local_window"
FAST_CUT_RENDERER_VERSION = "three_band_default_v7_standalone_curve_no_energy_floor"
TARGET_ENERGY_PLANNER_VERSION = "target_energy_default_render_v2_energy_curve_stable_section"
TARGET_STYLE_PLANNER_VERSION = "target_style_default_render_v1_style_contrast_smooth_handoff"
FAST_CUT_HIGH_SCORE_TOLERANCE = 0.08


def plan_default_transition(
    prev_song: Any,
    next_song: Any,
    *,
    cursor_sec: float = 0.0,
    compatibility_bridge: bool = False,
) -> dict[str, Any]:
    """Return a default_mix transition package.

    ``compatibility_bridge`` keeps the response acceptable to the current mobile
    assertion by exposing section_match/eq_band_mix while preserving default
    metadata under ``default_mix``.
    """
    prev_features = default_features(prev_song)
    next_features = default_features(next_song)
    strategy_num, strategy_name, reason = StrategySelector.select(
        FeatureAnalyzer.extract_features(_feature_payload(prev_song, prev_features)),
        FeatureAnalyzer.extract_features(_feature_payload(next_song, next_features)),
        user_strategy="auto",
    )
    duration_sec = _default_duration_for_strategy(strategy_num)
    exit_choice = select_exit_candidate(prev_song, cursor_sec=cursor_sec, fade_sec=duration_sec)
    entry_choice = select_entry_candidate(
        next_song,
        prev_song=prev_song,
        from_at_sec=exit_choice["time"],
        fade_sec=duration_sec,
    )
    alignment = refine_default_transition_alignment(
        prev_song,
        next_song,
        from_at_sec=exit_choice["time"],
        to_at_sec=entry_choice["time"],
        fade_sec=duration_sec,
        cursor_sec=cursor_sec,
    )
    from_at = alignment["from_at_sec"]
    to_at = alignment["to_at_sec"]
    audio_feature_source = _default_audio_feature_source(exit_choice, entry_choice)
    pair_id = pair_id_for(
        prev_song,
        next_song,
        from_at,
        to_at,
        duration_sec=duration_sec,
        audio_feature_source=audio_feature_source,
    )
    exit_selection_reason = _selection_reason("exit", exit_choice)
    entry_selection_reason = _selection_reason("entry", entry_choice)
    beat_alignment_shift_ms = round(
        (
            abs(float(from_at) - float(exit_choice.get("time", from_at)))
            + abs(float(to_at) - float(entry_choice.get("time", to_at)))
        )
        * 1000.0,
        3,
    )
    phrase_anchor_used = any(
        "phrase" in str(value).lower()
        for value in (
            exit_choice.get("source"),
            entry_choice.get("source"),
            alignment.get("from_anchor"),
            alignment.get("to_anchor"),
        )
    )
    entry_breakdown = entry_choice.get("breakdown") if isinstance(entry_choice.get("breakdown"), dict) else {}
    vocal_penalty_score = round(
        float(entry_breakdown.get("overlap_vocal_conflict") or 0.0)
        + max(0.0, 1.0 - float(entry_breakdown.get("vocal_entry_sparsity") or 1.0)),
        4,
    )
    metadata = {
        "source": "default_mix_v2_scored_alignment",
        "planner_version": PLANNER_VERSION,
        "required_renderer_version": REQUIRED_RENDERER_VERSION,
        "audio_feature_source": audio_feature_source,
        "analysis_missing": audio_feature_source != REQUIRED_AUDIO_FEATURE_SOURCE,
        "pair_id": pair_id,
        "from_song_id": _song_id(prev_song),
        "to_song_id": _song_id(next_song),
        "from_at_sec": round(from_at, 3),
        "to_at_sec": round(to_at, 3),
        "resume_at_sec": round(to_at + duration_sec, 3),
        "duration_sec": round(duration_sec, 3),
        "strategy_num": strategy_num,
        "strategy": strategy_name,
        "selection_reason": reason,
        "exit_selection_reason": exit_selection_reason,
        "entry_selection_reason": entry_selection_reason,
        "phrase_anchor_used": phrase_anchor_used,
        "beat_alignment_shift_ms": beat_alignment_shift_ms,
        "vocal_penalty_score": vocal_penalty_score,
        "energy_match_gain_db": None,
        "features1": prev_features,
        "features2": next_features,
        "cut_point_policy": {
            "exit_source": exit_choice.get("source") or exit_source(prev_song),
            "entry_source": entry_choice.get("source") or entry_source(next_song),
            "transition_windows_role": "candidate_regions_only",
            "scoring": "exit/entry bar-level scorer with vocal, drum, energy and handoff features",
            "alignment": "nearest beat/downbeat plus local drum anchor refinement",
            "fallback": "explicit emergency fallback only when dj_structure_v2 is missing",
        },
        "exit_candidate": exit_choice,
        "entry_candidate": entry_choice,
        "alignment": alignment,
    }
    if not compatibility_bridge:
        return {
            "transition_mode": "default_mix",
            "execution_mode": "default_render_playback",
            "rule_key": "default_mix:auto",
            "rule_label_zh": "默认混音",
            "from_at_sec": metadata["from_at_sec"],
            "to_at_sec": metadata["to_at_sec"],
            "start_in_prev": metadata["from_at_sec"],
            "start_in_next": metadata["to_at_sec"],
            "duration_sec": metadata["duration_sec"],
            "fade_sec": metadata["duration_sec"],
            "pair_id": pair_id,
            "transition_render_url": None,
            "transition_render_meta_url": None,
            "default_mix": metadata,
            "source": "default_mix_v2_scored_alignment",
            "reason": [
                "Default mix planner scored beat/downbeat candidates inside cached analysis regions.",
                "RK default render playback can consume transition_render resources when available.",
            ],
        }

    plan = eq_transition_strategy.generate_eq_band_mix_transition(
        prev_song,
        next_song,
        from_at_sec=from_at,
        to_at_sec=to_at,
        strategy_num=strategy_num,
        strategy_name=strategy_name,
        selection_reason=f"default_mix bridge: {reason}",
        features1=metadata["features1"],
        features2=metadata["features2"],
        transition_mode="section_match",
        eq_mix_user_mode="auto",
        fallback={},
        rule_key_prefix="section_match",
        transition_seed=f"default-bridge|{pair_id}",
    )
    plan["rule_key"] = "section_match:default_mix_bridge"
    plan["rule_label_zh"] = "默认混音桥接"
    plan["source"] = "default_mix_v2_scored_alignment"
    plan["default_mix"] = metadata
    plan["section_match"] = {
        "score": 100.0,
        "quality": "default_mix_bridge",
        "strategy_reason": "Default mix phase-0 compatibility bridge.",
        "a_section": {
            "direction": "out",
            "label": "default_exit",
            "start": metadata["from_at_sec"],
            "cut_point_source": metadata["cut_point_policy"]["exit_source"],
            "candidate_score": exit_choice.get("score"),
        },
        "b_section": {
            "direction": "in",
            "label": "default_entry",
            "start": metadata["to_at_sec"],
            "cut_point_source": metadata["cut_point_policy"]["entry_source"],
            "candidate_score": entry_choice.get("score"),
        },
        "is_fallback": False,
        "default_mix_bridge": True,
        "cut_point_policy": metadata["cut_point_policy"],
    }
    plan.setdefault("reason", []).append(
        "Default mix metadata is wrapped as section_match/eq_band_mix for current mobile compatibility."
    )
    return plan


def plan_fast_cut_transition(
    prev_song: Any,
    next_song: Any,
    *,
    exit_time_sec: float | None = None,
    cursor_sec: float | None = None,
    min_exit_sec: float | None = None,
    max_exit_sec: float | None = None,
    render_budget_sec: float | None = None,
    fade_sec: float | None = None,
    track2_scan_mode: str = "phrase_change",
    require_precomputed_v2: bool = True,
) -> dict[str, Any]:
    """Return a default-render plan for a user-triggered fast cut.

    ``exit_time_sec`` is kept for old clients.  New clients pass the live cursor
    plus an exit window so Track1 can keep playing while Track2 is scanned and
    the pair render is generated.
    """
    prev_duration = float(getattr(prev_song, "duration", None) or 0.0)
    if exit_time_sec is None and min_exit_sec is None and cursor_sec is None:
        raise ValueError("exit_time_sec or cursor_sec/min_exit_sec is required")

    requested_exit = float(
        exit_time_sec
        if exit_time_sec is not None
        else min_exit_sec
        if min_exit_sec is not None
        else cursor_sec
    )
    live_cursor = float(cursor_sec if cursor_sec is not None else requested_exit)
    if requested_exit < 1.0:
        raise ValueError("exit_time_sec must be >= 1.0")

    latest = prev_duration - 2.0 if prev_duration > 0 else None
    if latest is not None and requested_exit > latest:
        raise ValueError("exit_time_sec must be <= track1 duration - 2.0")

    if min_exit_sec is None and max_exit_sec is None:
        window_min = requested_exit
        window_max = requested_exit
    else:
        window_min = float(min_exit_sec if min_exit_sec is not None else max(1.0, live_cursor + 3.0))
        window_max = float(max_exit_sec if max_exit_sec is not None else window_min + 5.0)
    window_min = max(1.0, window_min)
    window_max = max(window_min, window_max)
    if latest is not None:
        window_min = min(window_min, latest)
        window_max = min(window_max, latest)

    prev_features = default_features(prev_song)
    next_features = default_features(next_song)
    strategy_num, strategy_name, reason = StrategySelector.select(
        FeatureAnalyzer.extract_features(_feature_payload(prev_song, prev_features)),
        FeatureAnalyzer.extract_features(_feature_payload(next_song, next_features)),
        user_strategy="auto",
    )
    duration_sec = float(fade_sec) if fade_sec is not None else _default_duration_for_strategy(strategy_num)
    duration_sec = max(3.0, min(12.0, duration_sec))

    exit_choice = select_fast_cut_exit_candidate(
        prev_song,
        cursor_sec=live_cursor,
        min_exit_sec=window_min,
        max_exit_sec=window_max,
        requested_exit_sec=requested_exit,
        fade_sec=duration_sec,
        require_precomputed_v2=require_precomputed_v2,
    )
    selected_exit = float(exit_choice["time"])
    target_energy = _energy_in_range(prev_song, max(0.0, selected_exit - duration_sec), selected_exit)
    exit_choice.setdefault("breakdown", {})
    if isinstance(exit_choice["breakdown"], dict):
        exit_choice["breakdown"]["requested_exit_time_sec"] = round(requested_exit, 3)
        exit_choice["breakdown"]["target_transition_energy"] = round(target_energy, 4)

    # The verified fast-cut path scans only the persisted Track2 v2 entry
    # candidates. It must not fall back to boundary metadata or runtime audio
    # analysis, otherwise a click can produce a different plan than the one
    # measured during the full-library backfill validation.
    entry_choice = select_fast_cut_track2_entry_candidate(
        next_song,
        prev_song=prev_song,
        from_at_sec=selected_exit,
        fade_sec=duration_sec,
        scan_mode=track2_scan_mode,
    )
    entry_choice = dict(entry_choice)
    alignment = refine_default_transition_alignment(
        prev_song,
        next_song,
        from_at_sec=selected_exit,
        to_at_sec=entry_choice["time"],
        fade_sec=duration_sec,
        cursor_sec=live_cursor,
        enforce_min_exit_floor=False,
    )
    from_at = float(alignment["from_at_sec"])
    nearest_future_v2 = (
        exit_choice.get("fast_cut_window_status")
        == "nearest_future_v2_candidate"
    )
    if nearest_future_v2:
        # The fallback is deliberately an already-labelled v2 candidate, so
        # use that exact point instead of snapping it back into an empty
        # preferred window.
        from_at = float(exit_choice["time"])
        alignment = {
            **alignment,
            "from_at_sec": round(from_at, 3),
            "from_anchor": exit_choice.get("anchor") or "v2_candidate",
            "nearest_future_v2_candidate": True,
        }
    elif not window_min <= from_at <= window_max:
        # Beat snapping must never pull a live cut outside its executable
        # window. Preserve the scored candidate when the nearest grid point is
        # outside the caller's deadline.
        from_at = min(window_max, max(window_min, selected_exit))
        alignment = {
            **alignment,
            "from_at_sec": round(from_at, 3),
            "from_anchor": exit_choice.get("anchor") or "window_candidate",
            "window_constraint_applied": True,
        }
    to_at = alignment["to_at_sec"]
    audio_feature_source = _default_audio_feature_source(exit_choice, entry_choice)
    if require_precomputed_v2 and audio_feature_source != REQUIRED_AUDIO_FEATURE_SOURCE:
        raise ValueError(
            "fast-cut v2 structure unavailable: both Track1 exit and Track2 entry "
            "must come from dj_structure_precomputed_window_v2"
        )
    pair_id = fast_cut_pair_id_for(
        prev_song,
        next_song,
        requested_exit,
        from_at,
        to_at,
        duration_sec=duration_sec,
        audio_feature_source=audio_feature_source,
        track2_scan_mode=track2_scan_mode,
    )
    exit_selection_reason = _selection_reason("exit", exit_choice)
    entry_selection_reason = _selection_reason("entry", entry_choice)
    beat_alignment_shift_ms = round(
        (
            abs(float(from_at) - float(exit_choice.get("time", selected_exit)))
            + abs(float(to_at) - float(entry_choice.get("time", to_at)))
        )
        * 1000.0,
        3,
    )
    entry_breakdown = entry_choice.get("breakdown") if isinstance(entry_choice.get("breakdown"), dict) else {}
    vocal_penalty_score = round(
        float(entry_breakdown.get("overlap_vocal_conflict") or 0.0)
        + max(0.0, 1.0 - float(entry_breakdown.get("vocal_entry_sparsity") or 1.0)),
        4,
    )
    fast_cut = {
        "manual_exit": True,
        "requested_exit_time_sec": round(requested_exit, 3),
        "requested_cursor_sec": round(live_cursor, 3),
        "min_exit_sec": round(window_min, 3),
        "max_exit_sec": round(window_max, 3),
        "aligned_from_at_sec": round(from_at, 3),
        "track2_scan_mode": track2_scan_mode or "phrase_change",
        "track2_entry_choice": entry_choice,
        "track2_entry_selection_reason": entry_selection_reason,
        "exit_window_status": exit_choice.get("fast_cut_window_status"),
        "exit_window_miss_sec": exit_choice.get("fast_cut_window_miss_sec"),
        "render_budget_sec": render_budget_sec,
        "target_transition_energy": round(target_energy, 4),
    }
    metadata = {
        "source": "default_mix_fast_cut_live_window_v2",
        "mode": "quick_manual_exit",
        "playback_mode": "fast_cut",
        "planner_version": FAST_CUT_PLANNER_VERSION if require_precomputed_v2 else PLANNER_VERSION,
        "required_renderer_version": FAST_CUT_RENDERER_VERSION if require_precomputed_v2 else REQUIRED_RENDERER_VERSION,
        "audio_feature_source": audio_feature_source,
        "analysis_missing": audio_feature_source != REQUIRED_AUDIO_FEATURE_SOURCE,
        "pair_id": pair_id,
        "from_song_id": _song_id(prev_song),
        "to_song_id": _song_id(next_song),
        "requested_exit_time_sec": round(requested_exit, 3),
        "requested_cursor_sec": round(live_cursor, 3),
        "min_exit_sec": round(window_min, 3),
        "max_exit_sec": round(window_max, 3),
        "from_at_sec": round(from_at, 3),
        "to_at_sec": round(to_at, 3),
        "resume_at_sec": round(to_at + duration_sec, 3),
        "duration_sec": round(duration_sec, 3),
        "strategy_num": strategy_num,
        "strategy": strategy_name,
        "selection_reason": f"fast_cut live window exit; Track2 scanned entry scoring: {reason}",
        "exit_selection_reason": exit_selection_reason,
        "entry_selection_reason": entry_selection_reason,
        "phrase_anchor_used": "phrase" in str(entry_choice.get("source") or "").lower(),
        "beat_alignment_shift_ms": beat_alignment_shift_ms,
        "vocal_penalty_score": vocal_penalty_score,
        "energy_match_gain_db": None,
        "features1": prev_features,
        "features2": next_features,
        "cut_point_policy": {
            "exit_source": exit_choice.get("source") or "fast_cut_window",
            "entry_source": entry_choice.get("source") or entry_source(next_song),
            "transition_windows_role": "candidate_regions_only_for_track2_entry",
            "scoring": "live Track1 exit window plus Track2 phrase/bar/beat candidate scorer",
            "alignment": "nearest beat/downbeat plus local phrase phase refinement",
            "fallback": (
                "nearest future v2 candidate only; legacy/raw fallback disabled"
                if require_precomputed_v2
                else "beat/downbeat/bar metadata from MP3 analysis"
            ),
        },
        "exit_candidate": exit_choice,
        "entry_candidate": entry_choice,
        "alignment": alignment,
        "fast_cut": fast_cut,
    }
    return {
        "ok": True,
        "transition_mode": "default_mix",
        "execution_mode": "default_render_playback",
        "playback_mode": "fast_cut",
        "rule_key": "default_mix:fast_cut",
        "rule_label_zh": "fast_cut",
        "from_song_id": metadata["from_song_id"],
        "to_song_id": metadata["to_song_id"],
        "requested_exit_time_sec": metadata["requested_exit_time_sec"],
        "requested_cursor_sec": metadata["requested_cursor_sec"],
        "min_exit_sec": metadata["min_exit_sec"],
        "max_exit_sec": metadata["max_exit_sec"],
        "from_at_sec": metadata["from_at_sec"],
        "to_at_sec": metadata["to_at_sec"],
        "start_in_prev": metadata["from_at_sec"],
        "start_in_next": metadata["to_at_sec"],
        "resume_at_sec": metadata["resume_at_sec"],
        "duration_sec": metadata["duration_sec"],
        "fade_sec": metadata["duration_sec"],
        "pair_id": pair_id,
        "transition_render_url": None,
        "transition_render_meta_url": None,
        "render_ready": False,
        "override_next_transition": True,
        "fast_cut": fast_cut,
        "default_mix": metadata,
        "source": "default_mix_fast_cut_live_window_v2",
        "reason": [
            "Fast-cut chooses a Track1 exit inside the live execution window.",
            "Track2 entry uses the fast-cut phrase/bar/beat candidate scorer.",
            "RK consumes the generated resources through default_render_playback.",
        ],
    }


def plan_target_energy_transition(
    prev_song: Any,
    next_song: Any,
    *,
    cursor_sec: float,
    target_min: float,
    target_max: float,
    max_wait_sec: float = 5.0,
    render_budget_sec: float | None = None,
    fade_sec: float | None = None,
    current_reference_energy_100: float | None = None,
) -> dict[str, Any]:
    """Return a default-render plan for target-energy cuts.

    Target energy is evaluated on the stable Track2 section after handoff, not
    on the overlap itself. The overlap stays optimized for continuity.
    """
    prev_duration = float(getattr(prev_song, "duration", None) or 0.0)
    live_cursor = max(0.0, float(cursor_sec or 0.0))
    latest = prev_duration - 2.0 if prev_duration > 0 else None
    window_min = live_cursor + 2.0
    window_max = live_cursor + max(2.0, float(max_wait_sec or 5.0))
    if latest is not None:
        window_min = min(window_min, latest)
        window_max = min(window_max, latest)
    window_max = max(window_min, window_max)

    prev_features = default_features(prev_song)
    next_features = default_features(next_song)
    strategy_num, strategy_name, reason = StrategySelector.select(
        FeatureAnalyzer.extract_features(_feature_payload(prev_song, prev_features)),
        FeatureAnalyzer.extract_features(_feature_payload(next_song, next_features)),
        user_strategy="auto",
    )
    duration_sec = float(fade_sec) if fade_sec is not None else _default_duration_for_strategy(strategy_num)
    duration_sec = max(3.0, min(12.0, duration_sec))

    exit_choice = select_fast_cut_exit_candidate(
        prev_song,
        cursor_sec=live_cursor,
        min_exit_sec=window_min,
        max_exit_sec=window_max,
        requested_exit_sec=window_min,
        fade_sec=duration_sec,
    )
    selected_exit = float(exit_choice["time"])
    current_reference_energy = (
        _energy_100_to_unit(float(current_reference_energy_100))
        if current_reference_energy_100 is not None
        else _energy_in_range(
            prev_song,
            max(0.0, selected_exit - duration_sec),
            selected_exit,
        )
    )
    entry_choice = select_target_energy_entry_candidate(
        next_song,
        prev_song=prev_song,
        from_at_sec=selected_exit,
        fade_sec=duration_sec,
        target_min=target_min,
        target_max=target_max,
        current_reference_energy=current_reference_energy,
    )
    alignment = refine_default_transition_alignment(
        prev_song,
        next_song,
        from_at_sec=selected_exit,
        to_at_sec=entry_choice["time"],
        fade_sec=duration_sec,
        cursor_sec=live_cursor,
        enforce_min_exit_floor=False,
    )
    from_at = alignment["from_at_sec"]
    to_at = alignment["to_at_sec"]
    audio_feature_source = _default_audio_feature_source(exit_choice, entry_choice)
    pair_id = target_energy_pair_id_for(
        prev_song,
        next_song,
        from_at,
        to_at,
        target_min=target_min,
        target_max=target_max,
        duration_sec=duration_sec,
        audio_feature_source=audio_feature_source,
    )
    target_energy = entry_choice.get("target_energy") if isinstance(entry_choice.get("target_energy"), dict) else {}
    entry_breakdown = entry_choice.get("breakdown") if isinstance(entry_choice.get("breakdown"), dict) else {}
    beat_alignment_shift_ms = round(
        (
            abs(float(from_at) - float(exit_choice.get("time", selected_exit)))
            + abs(float(to_at) - float(entry_choice.get("time", to_at)))
        )
        * 1000.0,
        3,
    )
    metadata = {
        "source": "target_energy_default_render",
        "mode": "target_energy_bucket",
        "playback_mode": "target_energy_cut",
        "planner_version": TARGET_ENERGY_PLANNER_VERSION,
        "base_default_planner_version": PLANNER_VERSION,
        "required_renderer_version": REQUIRED_RENDERER_VERSION,
        "audio_feature_source": audio_feature_source,
        "analysis_missing": audio_feature_source != REQUIRED_AUDIO_FEATURE_SOURCE,
        "pair_id": pair_id,
        "from_song_id": _song_id(prev_song),
        "to_song_id": _song_id(next_song),
        "requested_cursor_sec": round(live_cursor, 3),
        "min_exit_sec": round(window_min, 3),
        "max_exit_sec": round(window_max, 3),
        "from_at_sec": round(from_at, 3),
        "to_at_sec": round(to_at, 3),
        "resume_at_sec": round(to_at + duration_sec, 3),
        "duration_sec": round(duration_sec, 3),
        "strategy_num": strategy_num,
        "strategy": strategy_name,
        "selection_reason": f"target energy stable-section scorer: {reason}",
        "exit_selection_reason": _selection_reason("exit", exit_choice),
        "entry_selection_reason": _selection_reason("entry", entry_choice),
        "phrase_anchor_used": "phrase" in str(entry_choice.get("source") or "").lower(),
        "beat_alignment_shift_ms": beat_alignment_shift_ms,
        "vocal_penalty_score": round(
            float(entry_breakdown.get("overlap_vocal_conflict") or 0.0)
            + max(0.0, 1.0 - float(entry_breakdown.get("vocal_safety_score") or 1.0)),
            4,
        ),
        "energy_match_gain_db": None,
        "features1": prev_features,
        "features2": next_features,
        "cut_point_policy": {
            "exit_source": exit_choice.get("source") or "target_energy_exit_window",
            "entry_source": entry_choice.get("source") or entry_source(next_song),
            "transition_windows_role": "track2 stable-energy entry candidates",
            "scoring": "target stable section energy first, pair smoothness second",
            "alignment": "nearest beat/downbeat plus phrase phase refinement",
            "fallback": "explicit fallback when dj_structure_v2 entry candidates are missing",
        },
        "exit_candidate": exit_choice,
        "entry_candidate": entry_choice,
        "alignment": alignment,
        "target_energy": target_energy,
        "render_budget_sec": render_budget_sec,
    }
    return {
        "ok": True,
        "transition_mode": "default_mix",
        "execution_mode": "default_render_playback",
        "playback_mode": "target_energy_cut",
        "rule_key": "target_energy:default_render",
        "rule_label_zh": "目标能量默认混音",
        "from_song_id": metadata["from_song_id"],
        "to_song_id": metadata["to_song_id"],
        "requested_cursor_sec": metadata["requested_cursor_sec"],
        "min_exit_sec": metadata["min_exit_sec"],
        "max_exit_sec": metadata["max_exit_sec"],
        "from_at_sec": metadata["from_at_sec"],
        "to_at_sec": metadata["to_at_sec"],
        "start_in_prev": metadata["from_at_sec"],
        "start_in_next": metadata["to_at_sec"],
        "resume_at_sec": metadata["resume_at_sec"],
        "duration_sec": metadata["duration_sec"],
        "fade_sec": metadata["duration_sec"],
        "pair_id": pair_id,
        "transition_render_url": None,
        "transition_render_meta_url": None,
        "render_ready": False,
        "override_next_transition": True,
        "target_energy": target_energy,
        "default_mix": metadata,
        "source": "target_energy_default_render",
        "reason": [
            "Target energy is measured on the stable Track2 section after handoff.",
            "The overlap uses default render playback to preserve continuity.",
        ],
    }


def plan_target_style_transition(
    prev_song: Any,
    next_song: Any,
    *,
    cursor_sec: float,
    target_style: str,
    current_style: str | None = None,
    target_style_score: float | None = None,
    style_contrast_score: float | None = None,
    max_wait_sec: float = 5.0,
    render_budget_sec: float | None = None,
    fade_sec: float | None = None,
) -> dict[str, Any]:
    """Return a default-render plan for target-style cuts.

    Style is a song-level target; the overlap still uses the same fast-cut
    Track1 live window and Track2 phrase/bar/beat entry scorer as default
    render playback.
    """
    live_cursor = max(0.0, float(cursor_sec or 0.0))
    prev_duration = float(getattr(prev_song, "duration", None) or 0.0)
    if prev_duration > 0:
        # This plan is used to rank target-style song candidates during
        # preview. Keep its scoring window valid near Track1's end; the real
        # cut is replanned from the current RK cursor after confirmation.
        scoring_lead = max(2.0, float(max_wait_sec or 5.0))
        live_cursor = min(live_cursor, max(0.0, prev_duration - scoring_lead - 2.0))
    plan = plan_fast_cut_transition(
        prev_song,
        next_song,
        cursor_sec=live_cursor,
        min_exit_sec=live_cursor + 2.0,
        max_exit_sec=live_cursor + max(2.0, float(max_wait_sec or 5.0)),
        render_budget_sec=render_budget_sec,
        fade_sec=fade_sec,
        track2_scan_mode="phrase_change",
        require_precomputed_v2=False,
    )
    metadata = plan.get("default_mix") if isinstance(plan.get("default_mix"), dict) else {}
    duration_sec = float(metadata.get("duration_sec") or plan.get("duration_sec") or 6.5)
    from_at = float(metadata.get("from_at_sec") or plan.get("from_at_sec") or 0.0)
    to_at = float(metadata.get("to_at_sec") or plan.get("to_at_sec") or 0.0)
    audio_feature_source = str(metadata.get("audio_feature_source") or "")
    pair_id = target_style_pair_id_for(
        prev_song,
        next_song,
        from_at,
        to_at,
        target_style=target_style,
        duration_sec=duration_sec,
        audio_feature_source=audio_feature_source,
    )
    target_style_meta = {
        "target_style": target_style,
        "current_style": current_style,
        "target_style_score": round(float(target_style_score), 4) if target_style_score is not None else None,
        "style_contrast_score": round(float(style_contrast_score), 4) if style_contrast_score is not None else None,
    }

    metadata.update({
        "source": "target_style_default_render",
        "mode": "target_dance_style",
        "playback_mode": "target_style_cut",
        "planner_version": TARGET_STYLE_PLANNER_VERSION,
        "base_default_planner_version": PLANNER_VERSION,
        "pair_id": pair_id,
        "selection_reason": f"target style default-render scorer: {metadata.get('selection_reason', '')}",
        "target_style": target_style_meta,
    })
    cut_policy = metadata.get("cut_point_policy") if isinstance(metadata.get("cut_point_policy"), dict) else {}
    cut_policy.update({
        "transition_windows_role": "candidate_regions_only_for_target_style_entry",
        "scoring": "target style contrast first at song selection, default render smoothness at pair planning",
        "alignment": "nearest beat/downbeat plus local phrase phase refinement",
    })
    metadata["cut_point_policy"] = cut_policy

    plan.update({
        "transition_mode": "default_mix",
        "execution_mode": "default_render_playback",
        "playback_mode": "target_style_cut",
        "rule_key": "target_style:default_render",
        "rule_label_zh": "目标风格默认混音",
        "pair_id": pair_id,
        "source": "target_style_default_render",
        "target_style": target_style_meta,
        "default_mix": metadata,
        "override_next_transition": True,
        "render_ready": False,
        "reason": [
            "Target style is selected by style contrast and target-style confidence.",
            "The overlap uses default render playback to preserve continuity.",
            "RK consumes the generated resources through default_render_playback.",
        ],
    })
    return plan


def default_features(song: Any) -> dict[str, float]:
    bands = band_density(song)
    music_features = getattr(song, "music_features", None) or {}
    dj = music_features.get("dj") if isinstance(music_features.get("dj"), dict) else {}
    return {
        "bpm": float(getattr(song, "bpm", None) or music_features.get("bpm") or 120.0),
        "energy": clamp01(getattr(song, "energy", None), 0.5),
        "bass_strength": clamp01(bands["low"], 0.5),
        "low_ratio": clamp01(bands["low"], 0.5),
        "mid_ratio": clamp01(bands["mid"], 0.5),
        "high_ratio": clamp01(bands["high"], 0.5),
        "vocal_density": clamp01(dj.get("vocal_density") or bands["mid"], 0.5),
    }


def select_exit_sec(song: Any, *, cursor_sec: float = 0.0) -> float:
    return select_exit_candidate(song, cursor_sec=cursor_sec)["time"]


def select_entry_sec(next_song: Any, *, prev_song: Any, from_at_sec: float) -> float:
    return select_entry_candidate(next_song, prev_song=prev_song, from_at_sec=from_at_sec)["time"]


def select_exit_candidate(song: Any, *, cursor_sec: float = 0.0, fade_sec: float = 6.5) -> dict[str, Any]:
    duration = float(getattr(song, "duration", None) or 0.0)
    min_time = max(20.0, float(cursor_sec or 0.0))
    downbeats = _float_list(getattr(song, "downbeats", None))
    beats = _float_list(getattr(song, "beat_points", None))
    structure_points = _candidate_points_from_dj_structure(
        song,
        role="exit",
        min_time=min_time,
        max_time=(duration * 0.92 if duration > 0 else None),
    )
    if structure_points:
        structure_scored = score_exit_candidates(song, structure_points, cursor_sec=cursor_sec, fade_sec=fade_sec)
        if _dj_structure(song).get("version") == "dj_structure_v2" and structure_scored:
            chosen = dict(structure_scored[0])
            chosen["dj_structure_v2_used"] = True
            chosen["dj_structure_v1_used"] = False
            chosen["dense_boundary_scan_used"] = False
            chosen.setdefault("audio_feature_source", REQUIRED_AUDIO_FEATURE_SOURCE)
            chosen["candidate_count"] = len(structure_points)
            chosen["structure_candidate_count"] = len(structure_points)
            chosen["dense_boundary_candidate_count"] = 0
            return chosen
        if structure_scored and _source_candidate_score(structure_scored[0]) >= 0.85:
            chosen = dict(structure_scored[0])
            chosen["analysis_missing"] = True
            chosen["fallback_used"] = True
            chosen["fallback_reason"] = "dj_structure_v2_missing_or_not_selected"
            chosen["dj_structure_v1_used"] = True
            chosen["dense_boundary_scan_used"] = False
            chosen["candidate_count"] = len(structure_points)
            chosen["structure_candidate_count"] = len(structure_points)
            chosen["dense_boundary_candidate_count"] = 0
            return chosen
        dense_points = _dense_boundary_candidates(
            song,
            role="exit",
            min_time=max(min_time, duration * 0.55 if duration > 0 else min_time),
            max_time=(duration * 0.92 if duration > 0 else None),
            source_prefix="dense",
        )
        combined_points = _dedupe_candidate_times(
            structure_points + dense_points,
            max_points=64,
        )
        scored = score_exit_candidates(song, combined_points, cursor_sec=cursor_sec, fade_sec=fade_sec)
        if scored:
            chosen = dict(scored[0])
            chosen["analysis_missing"] = True
            chosen["fallback_used"] = True
            chosen["fallback_reason"] = "dj_structure_v2_missing_dense_boundary_scan"
            chosen["dj_structure_v1_used"] = True
            chosen["dense_boundary_scan_used"] = True
            chosen["candidate_count"] = len(combined_points)
            chosen["structure_candidate_count"] = len(structure_points)
            chosen["dense_boundary_candidate_count"] = len(dense_points)
            return chosen
    points = _candidate_points_from_regions(
        song,
        role="exit",
        min_time=min_time,
        max_time=(duration * 0.92 if duration > 0 else None),
        fallback_start=(duration * 0.76 if duration > 0 else min_time),
        fallback_end=(duration - 2.0 if duration > 0 else None),
        downbeats=downbeats,
        beats=beats,
    )
    scored = score_exit_candidates(song, points, cursor_sec=cursor_sec, fade_sec=fade_sec)
    if scored:
        return scored[0]
    fallback = max(min_time, min(duration - 8.0, duration * 0.80)) if duration > 0 else min_time
    return {
        "time": round(fallback, 3),
        "score": 0.0,
        "source": "duration_fallback",
        "breakdown": {},
    }


def select_entry_candidate(
    next_song: Any,
    *,
    prev_song: Any,
    from_at_sec: float,
    fade_sec: float = 6.5,
) -> dict[str, Any]:
    duration = float(getattr(next_song, "duration", None) or 0.0)
    downbeats = _float_list(getattr(next_song, "downbeats", None))
    beats = _float_list(getattr(next_song, "beat_points", None))
    upper = min(90.0, duration * 0.50) if duration > 0 else 90.0
    fallback_lower = _entry_fallback_lower_bound(duration, upper)
    prev_tail_energy = _energy_in_range(prev_song, from_at_sec, from_at_sec + fade_sec)
    structure_points = _candidate_points_from_dj_structure(
        next_song,
        role="entry",
        min_time=2.0,
        max_time=upper,
    )
    if structure_points:
        structure_scored = score_entry_candidates(
            next_song,
            structure_points,
            prev_tail_energy=prev_tail_energy,
            prev_vocal_events=getattr(prev_song, "vocal_events", None) or [],
            fade_sec=fade_sec,
        )
        if _dj_structure(next_song).get("version") == "dj_structure_v2" and structure_scored:
            chosen = dict(structure_scored[0])
            chosen["dj_structure_v2_used"] = True
            chosen["dj_structure_v1_used"] = False
            chosen["dense_boundary_scan_used"] = False
            chosen.setdefault("audio_feature_source", REQUIRED_AUDIO_FEATURE_SOURCE)
            chosen["candidate_count"] = len(structure_points)
            chosen["structure_candidate_count"] = len(structure_points)
            chosen["dense_boundary_candidate_count"] = 0
            return chosen
        if (
            structure_scored
            and _source_candidate_score(structure_scored[0]) >= 0.85
        ):
            chosen = dict(structure_scored[0])
            chosen["analysis_missing"] = True
            chosen["fallback_used"] = True
            chosen["fallback_reason"] = "dj_structure_v2_missing_or_not_selected"
            chosen["dj_structure_v1_used"] = True
            chosen["dense_boundary_scan_used"] = False
            chosen["candidate_count"] = len(structure_points)
            chosen["structure_candidate_count"] = len(structure_points)
            chosen["dense_boundary_candidate_count"] = 0
            return chosen
        dense_points = _dense_boundary_candidates(
            next_song,
            role="entry",
            min_time=2.0,
            max_time=upper,
            source_prefix="dense",
        )
        combined_points = _dedupe_candidate_times(
            structure_points + dense_points,
            max_points=64,
        )
        combined_points = _annotate_entry_candidates_with_audio(
            next_song,
            combined_points,
            prev_song=prev_song,
            from_at_sec=from_at_sec,
            fade_sec=fade_sec,
        )
        scored = score_entry_candidates(
            next_song,
            combined_points,
            prev_tail_energy=prev_tail_energy,
            prev_vocal_events=getattr(prev_song, "vocal_events", None) or [],
            fade_sec=fade_sec,
        )
        if scored:
            chosen = dict(scored[0])
            chosen["analysis_missing"] = True
            chosen["fallback_used"] = True
            chosen["fallback_reason"] = "dj_structure_v2_missing_dense_boundary_scan"
            chosen["dj_structure_v1_used"] = True
            chosen["dense_boundary_scan_used"] = True
            chosen["candidate_count"] = len(combined_points)
            chosen["structure_candidate_count"] = len(structure_points)
            chosen["dense_boundary_candidate_count"] = len(dense_points)
            return chosen
    points = _candidate_points_from_regions(
        next_song,
        role="entry",
        min_time=2.0,
        max_time=upper,
        fallback_start=fallback_lower,
        fallback_end=upper,
        downbeats=downbeats,
        beats=beats,
    )
    scored = score_entry_candidates(
        next_song,
        points,
        prev_tail_energy=prev_tail_energy,
        prev_vocal_events=getattr(prev_song, "vocal_events", None) or [],
        fade_sec=fade_sec,
    )
    if scored:
        return scored[0]
    fallback_points = _entry_safety_fallback_points(
        min_time=fallback_lower,
        max_time=upper,
        downbeats=downbeats,
        beats=beats,
    )
    fallback_scored = score_entry_candidates(
        next_song,
        fallback_points,
        prev_tail_energy=prev_tail_energy,
        prev_vocal_events=getattr(prev_song, "vocal_events", None) or [],
        fade_sec=fade_sec,
    )
    if fallback_scored:
        chosen = dict(fallback_scored[0])
        chosen["safety_fallback_used"] = True
        return chosen
    return {
        "time": round(float(fallback_lower), 3),
        "score": -1.0,
        "source": "no_usable_entry_fallback",
        "anchor": "raw",
        "entry_gate_passed": False,
        "entry_gate_failures": ["no_usable_entry_candidate"],
        "relaxed_entry_fallback": True,
        "breakdown": {
            "energy_match_score": 0.0,
            "drum_entry_strength": 0.0,
            "immediate_entry_punch": 0.0,
            "vocal_entry_sparsity": 0.0,
            "overlap_vocal_conflict": 0.0,
        },
    }


def select_fast_cut_exit_candidate(
    song: Any,
    *,
    cursor_sec: float,
    min_exit_sec: float,
    max_exit_sec: float,
    requested_exit_sec: float,
    fade_sec: float = 6.5,
    require_precomputed_v2: bool = True,
) -> dict[str, Any]:
    duration = float(getattr(song, "duration", None) or 0.0)
    latest = duration - 2.0 if duration > 0 else max_exit_sec
    lower = max(1.0, min(float(min_exit_sec), latest))
    upper = max(lower, min(float(max_exit_sec), latest))
    structure_points = _fast_cut_v2_exit_points(
        song,
        min_time=lower,
        max_time=upper,
    )
    if structure_points:
        scored = score_exit_candidates(
            song,
            structure_points,
            cursor_sec=cursor_sec,
            fade_sec=fade_sec,
        )
        if scored:
            # Prefer a near-15-second handoff without sacrificing material
            # local quality. This reserves the most time for render, sync,
            # and RK deck preparation on an unstable hotspot.
            best_score = float(scored[0].get("score") or 0.0)
            high_quality = [
                item
                for item in scored
                if float(item.get("score") or 0.0)
                >= best_score - FAST_CUT_HIGH_SCORE_TOLERANCE
            ]
            target = min(max(float(requested_exit_sec), lower), upper)
            chosen = min(
                high_quality,
                key=lambda item: (
                    abs(float(item["time"]) - target),
                    -float(item.get("score") or 0.0),
                    float(item["time"]),
                ),
            )
            chosen = dict(chosen)
            chosen["fast_cut_window_used"] = True
            chosen["fast_cut_window_status"] = "within_target_window"
            chosen["source"] = f"fast_cut_window.{chosen.get('source', 'dj_structure_v2')}"
            return chosen

    # Keep the transition on a real v2 local-feature candidate. If the
    # preferred 10-15s window is sparse, use the first future v2 candidate
    # rather than a raw beat/downbeat or an unlabeled time fallback.
    future_points = _fast_cut_v2_exit_points(
        song,
        min_time=upper,
        max_time=latest,
        inclusive_min=False,
    )
    if future_points:
        scored = score_exit_candidates(
            song,
            future_points,
            cursor_sec=cursor_sec,
            fade_sec=fade_sec,
        )
        if scored:
            chosen = min(
                scored,
                key=lambda item: (float(item["time"]), -float(item.get("score") or 0.0)),
            )
            chosen = dict(chosen)
            chosen["fast_cut_window_used"] = False
            chosen["fast_cut_window_status"] = "nearest_future_v2_candidate"
            chosen["fast_cut_window_miss_sec"] = round(float(chosen["time"]) - upper, 3)
            chosen["source"] = f"fast_cut_nearest_v2.{chosen.get('source', 'dj_structure_v2')}"
            return chosen

    if not require_precomputed_v2:
        boundary_points = _fast_cut_boundary_candidates(
            song,
            scan_mode="phrase_change",
            min_time=lower,
            max_time=upper,
        )
        scored = score_exit_candidates(
            song,
            boundary_points,
            cursor_sec=cursor_sec,
            fade_sec=fade_sec,
        )
        if scored:
            chosen = dict(scored[0])
            chosen["fast_cut_window_used"] = True
            chosen["fast_cut_window_status"] = "legacy_window_candidate"
            return chosen

        fallback_time = min(max(float(requested_exit_sec), lower), upper)
        return {
            "time": round(fallback_time, 3),
            "score": 0.0,
            "source": "fast_cut_requested_exit_fallback",
            "anchor": "raw",
            "fast_cut_window_used": True,
            "fast_cut_window_status": "legacy_requested_exit",
            "breakdown": {},
        }

    raise ValueError(
        "fast-cut v2 structure unavailable: no future Track1 v2 exit candidate"
    )


def select_fast_cut_track2_entry_candidate(
    next_song: Any,
    *,
    prev_song: Any,
    from_at_sec: float,
    fade_sec: float = 6.5,
    scan_mode: str = "phrase_change",
) -> dict[str, Any]:
    duration = float(getattr(next_song, "duration", None) or 0.0)
    upper = min(90.0, duration * 0.50) if duration > 0 else 90.0
    lower = 5.0 if upper > 5.0 else 2.0
    prev_tail_energy = _energy_in_range(prev_song, max(0.0, from_at_sec - fade_sec), from_at_sec)
    candidates: list[dict[str, Any]] = []

    for item in _candidate_points_from_dj_structure(
        next_song,
        role="entry",
        min_time=lower,
        max_time=upper,
    ):
        candidates.append({**item, "source": f"fast_cut.{item.get('source', 'dj_structure')}"})
    if not candidates:
        for item in _fast_cut_boundary_candidates(
            next_song,
            scan_mode=scan_mode,
            min_time=lower,
            max_time=upper,
        ):
            candidates.append(item)

    if not candidates:
        candidates = _candidate_points_from_regions(
            next_song,
            role="entry",
            min_time=lower,
            max_time=upper,
            fallback_start=_entry_fallback_lower_bound(duration, upper),
            fallback_end=upper,
            downbeats=_float_list(getattr(next_song, "downbeats", None)),
            beats=_float_list(getattr(next_song, "beat_points", None)),
        )

    candidates = _dedupe_candidate_times(candidates, max_points=64)
    candidates = _annotate_entry_candidates_with_audio(
        next_song,
        candidates,
        prev_song=prev_song,
        from_at_sec=from_at_sec,
        fade_sec=fade_sec,
    )
    scored = score_entry_candidates(
        next_song,
        candidates,
        prev_tail_energy=prev_tail_energy,
        prev_vocal_events=getattr(prev_song, "vocal_events", None) or [],
        fade_sec=fade_sec,
    )
    if scored:
        chosen = dict(scored[0])
        chosen["fast_cut_track2_scan_used"] = True
        chosen["scan_mode"] = scan_mode
        chosen["candidate_count"] = len(candidates)
        return chosen

    fallback = select_entry_candidate(
        next_song,
        prev_song=prev_song,
        from_at_sec=from_at_sec,
        fade_sec=fade_sec,
    )
    fallback = dict(fallback)
    fallback["fast_cut_track2_scan_used"] = False
    fallback["scan_fallback_used"] = True
    fallback["scan_mode"] = scan_mode
    return fallback


def select_target_energy_entry_candidate(
    next_song: Any,
    *,
    prev_song: Any,
    from_at_sec: float,
    fade_sec: float = 6.5,
    target_min: float,
    target_max: float,
    current_reference_energy: float,
) -> dict[str, Any]:
    duration = float(getattr(next_song, "duration", None) or 0.0)
    upper = min(90.0, duration * 0.55) if duration > 0 else 90.0
    lower = 5.0 if upper > 5.0 else 2.0
    candidates: list[dict[str, Any]] = []
    for item in _candidate_points_from_dj_structure(
        next_song,
        role="entry",
        min_time=lower,
        max_time=upper,
    ):
        candidates.append({**item, "source": f"target_energy.{item.get('source', 'dj_structure')}"})

    if not candidates:
        for item in _fast_cut_boundary_candidates(
            next_song,
            scan_mode="phrase_change",
            min_time=lower,
            max_time=upper,
        ):
            candidates.append({**item, "target_energy_fallback_used": True})

    if not candidates:
        candidates = _candidate_points_from_regions(
            next_song,
            role="entry",
            min_time=lower,
            max_time=upper,
            fallback_start=_entry_fallback_lower_bound(duration, upper),
            fallback_end=upper,
            downbeats=_float_list(getattr(next_song, "downbeats", None)),
            beats=_float_list(getattr(next_song, "beat_points", None)),
        )
        candidates = [{**item, "target_energy_fallback_used": True} for item in candidates]

    candidates = _dedupe_candidate_times(candidates, max_points=64)
    scored = score_target_energy_entry_candidates(
        next_song,
        candidates,
        prev_song=prev_song,
        from_at_sec=from_at_sec,
        fade_sec=fade_sec,
        target_min=target_min,
        target_max=target_max,
        current_reference_energy=current_reference_energy,
    )
    if scored:
        chosen = dict(scored[0])
        chosen["target_energy_entry_scan_used"] = True
        chosen["candidate_count"] = len(candidates)
        return chosen

    fallback = select_fast_cut_track2_entry_candidate(
        next_song,
        prev_song=prev_song,
        from_at_sec=from_at_sec,
        fade_sec=fade_sec,
        scan_mode="phrase_change",
    )
    fallback = dict(fallback)
    fallback["target_energy_entry_scan_used"] = False
    fallback["target_energy_fallback_used"] = True
    return fallback


def exit_source(song: Any) -> str:
    if _dj_structure(song).get("track1_exit_candidates"):
        version = str(_dj_structure(song).get("version") or "dj_structure")
        return f"{version}.track1_exit_candidates"
    return "stem_transition_windows" if getattr(song, "transition_windows", None) else "beat_bar"


def entry_source(song: Any) -> str:
    if _dj_structure(song).get("track2_entry_candidates"):
        version = str(_dj_structure(song).get("version") or "dj_structure")
        return f"{version}.track2_entry_candidates"
    return "stem_transition_windows" if getattr(song, "transition_windows", None) else "beat_bar"


def score_exit_candidates(
    song: Any,
    candidates: list[dict[str, Any]],
    *,
    cursor_sec: float = 0.0,
    fade_sec: float = 6.5,
) -> list[dict[str, Any]]:
    duration = float(getattr(song, "duration", None) or 0.0)
    bands = band_density(song)
    out: list[dict[str, Any]] = []
    for candidate in candidates:
        t = float(candidate["time"])
        end = min(duration, t + fade_sec) if duration > 0 else t + fade_sec
        window_start = max(0.0, t - fade_sec * 0.5)
        precomputed_vocal = _float(candidate.get("vocal_sparsity"), None)
        if precomputed_vocal is not None:
            vocal_sparsity = clamp01(precomputed_vocal, 0.0)
        else:
            vocal_density = _vocal_density(song, t, end)
            vocal_sparsity = 1.0 - vocal_density
        drum_stability = clamp01(
            candidate.get("drum_stability", candidate.get("drum_strength")),
            _drum_stability(song, t, end),
        )
        melodic_presence = clamp01(
            candidate.get("melodic_presence"),
            _melodic_presence(song, t, end, default=bands["mid"]),
        )
        fullness_score = clamp01(
            candidate.get("fullness_score", candidate.get("fullness")),
            _energy_in_range(song, max(0.0, t - 2.0), end),
        )
        tail_energy_score = clamp01(
            candidate.get("tail_energy_score"),
            _energy_in_range(song, window_start, end),
        )
        handoff_readiness = clamp01(
            candidate.get("handoff_readiness"),
            _handoff_readiness(song, t, end),
        )
        progress = t / duration if duration > 0 else 0.8
        progress_score = 1.0 - min(1.0, abs(progress - 0.78) / 0.24)
        cursor_score = 1.0 if t >= max(20.0, cursor_sec) else 0.0
        anchor_bonus = 0.05 if candidate.get("anchor") == "downbeat" else 0.02
        score = (
            0.23 * vocal_sparsity
            + 0.20 * drum_stability
            + 0.12 * (1.0 - melodic_presence)
            + 0.12 * fullness_score
            + 0.16 * handoff_readiness
            + 0.10 * tail_energy_score
            + 0.07 * progress_score
            + anchor_bonus
        ) * cursor_score
        out.append({
            **candidate,
            "time": round(t, 3),
            "score": round(float(score), 4),
            "breakdown": {
                "vocal_sparsity": round(vocal_sparsity, 4),
                "drum_stability": round(drum_stability, 4),
                "melodic_presence": round(melodic_presence, 4),
                "fullness_score": round(fullness_score, 4),
                "handoff_readiness": round(handoff_readiness, 4),
                "tail_energy_score": round(tail_energy_score, 4),
                "progress_score": round(progress_score, 4),
                "anchor_bonus": round(anchor_bonus, 4),
            },
        })
    return sorted(out, key=lambda item: (item["score"], item.get("region_score", 0.0)), reverse=True)


def score_entry_candidates(
    song: Any,
    candidates: list[dict[str, Any]],
    *,
    prev_tail_energy: float,
    prev_vocal_events: list[Any],
    fade_sec: float = 6.5,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for candidate in candidates:
        t = float(candidate["time"])
        end = t + fade_sec
        audio_entry_rms = _float(candidate.get("audio_entry_rms"), None)
        precomputed_entry_rms = _float(candidate.get("entry_rms", candidate.get("local_rms")), None)
        audio_prev_tail_rms = _float(candidate.get("audio_prev_tail_rms"), None)
        if audio_entry_rms is not None and audio_prev_tail_rms is not None and audio_prev_tail_rms > 1e-8:
            entry_energy = audio_entry_rms
            energy_match_score = 1.0 - min(
                1.0,
                abs(audio_entry_rms - audio_prev_tail_rms) / max(audio_entry_rms, audio_prev_tail_rms, 1e-8),
            )
        elif precomputed_entry_rms is not None:
            entry_energy = precomputed_entry_rms
            energy_match_score = 1.0 - min(1.0, abs(entry_energy - prev_tail_energy) / max(entry_energy, prev_tail_energy, 0.55))
        else:
            entry_energy = _energy_in_range(song, t, end)
            energy_match_score = 1.0 - min(1.0, abs(entry_energy - prev_tail_energy) / 0.55)
        drum_entry_strength = clamp01(
            candidate.get("audio_drum_entry_strength", candidate.get("drum_entry_strength", candidate.get("drum_strength"))),
            _drum_entry_strength(song, t, end),
        )
        immediate_entry_punch = clamp01(
            candidate.get("audio_immediate_entry_punch", candidate.get("immediate_entry_punch", candidate.get("immediate_punch"))),
            _energy_in_range(song, t, min(end, t + 2.0)),
        )
        audio_vocal_sparsity = _float(
            candidate.get("audio_vocal_entry_sparsity", candidate.get("vocal_entry_sparsity", candidate.get("vocal_sparsity"))),
            None,
        )
        if audio_vocal_sparsity is not None:
            vocal_entry_sparsity = clamp01(audio_vocal_sparsity, 0.0)
            vocal_density = 1.0 - vocal_entry_sparsity
        else:
            vocal_density = _vocal_density(song, t, end)
            vocal_entry_sparsity = 1.0 - vocal_density
        vocal_penalty = 1.0 - vocal_entry_sparsity
        prev_vocal = vocal_density_in_range(prev_vocal_events, 0.0, fade_sec)
        overlap_vocal_conflict = min(prev_vocal, vocal_density)
        anchor_bonus = 0.05 if candidate.get("anchor") == "downbeat" else 0.02
        score = (
            0.35 * energy_match_score
            + 0.18 * drum_entry_strength
            + 0.22 * immediate_entry_punch
            + 0.40 * vocal_entry_sparsity
            - 0.35 * vocal_penalty
            - 0.45 * overlap_vocal_conflict
            + anchor_bonus
        )
        gate_failures: list[str] = []
        vocal_gate_threshold = 0.50 if candidate.get("audio_feature_source") == "dj_structure_precomputed_window_v2" else 0.55
        if vocal_entry_sparsity < vocal_gate_threshold:
            gate_failures.append("vocal_entry_sparsity")
        if drum_entry_strength < 0.48:
            gate_failures.append("drum_entry_strength")
        if immediate_entry_punch < 0.42:
            gate_failures.append("immediate_entry_punch")
        energy_gate_reference = audio_prev_tail_rms if audio_prev_tail_rms is not None else prev_tail_energy
        if energy_gate_reference > 0.05 and entry_energy > energy_gate_reference * 1.10:
            gate_failures.append("entry_energy_too_hot")
        if _candidate_has_zero_source_score(candidate):
            gate_failures.append("source_entry_score_zero")
        if (
            energy_match_score <= 0.0
            and drum_entry_strength <= 0.0
            and immediate_entry_punch <= 0.0
            and vocal_entry_sparsity <= 0.0
        ):
            gate_failures.append("zero_entry_quality_metrics")
        out.append({
            **candidate,
            "time": round(t, 3),
            "score": round(float(score), 4),
            "entry_gate_passed": not gate_failures,
            "entry_gate_failures": gate_failures,
            "breakdown": {
                "energy_match_score": round(energy_match_score, 4),
                "drum_entry_strength": round(drum_entry_strength, 4),
                "immediate_entry_punch": round(immediate_entry_punch, 4),
                "vocal_entry_sparsity": round(vocal_entry_sparsity, 4),
                "vocal_penalty": round(vocal_penalty, 4),
                "overlap_vocal_conflict": round(overlap_vocal_conflict, 4),
                "anchor_bonus": round(anchor_bonus, 4),
                "audio_feature_source": candidate.get("audio_feature_source"),
                "local_rms": round(precomputed_entry_rms, 6) if precomputed_entry_rms is not None else None,
            },
        })
    strict = [item for item in out if item.get("entry_gate_passed")]
    if strict:
        return sorted(strict, key=lambda item: (item["score"], item.get("region_score", 0.0)), reverse=True)
    relaxed = sorted(
        [item for item in out if _relaxed_entry_candidate_allowed(item)],
        key=lambda item: (item["score"], item.get("region_score", 0.0)),
        reverse=True,
    )
    if relaxed:
        relaxed[0] = {**relaxed[0], "relaxed_entry_fallback": True}
    return relaxed


def score_target_energy_entry_candidates(
    song: Any,
    candidates: list[dict[str, Any]],
    *,
    prev_song: Any,
    from_at_sec: float,
    fade_sec: float = 6.5,
    target_min: float,
    target_max: float,
    current_reference_energy: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lo = _energy_100_to_unit(target_min)
    hi = _energy_100_to_unit(target_max)
    current_unit = clamp01(current_reference_energy, 0.5)
    current_100 = current_unit * 100.0
    target_direction = (
        "up"
        if float(target_min) > current_100 + 2.0
        else "down"
        if float(target_max) < current_100 - 2.0
        else "same"
    )
    prev_tail = _energy_in_range(prev_song, max(0.0, from_at_sec - fade_sec), from_at_sec)
    prev_vocal = vocal_density_in_range(getattr(prev_song, "vocal_events", None) or [], from_at_sec, from_at_sec + fade_sec)
    for candidate in candidates:
        t = float(candidate["time"])
        stable_start = t + fade_sec
        stable_end = stable_start + 14.0
        stable_energy = _candidate_stable_energy(song, candidate, stable_start, stable_end)
        entry_energy = _candidate_entry_energy(song, candidate, t, t + fade_sec)
        target_match = _energy_bucket_match_unit(stable_energy, lo, hi)
        target_100 = stable_energy * 100.0
        if target_direction == "up":
            delta_score = clamp01((target_100 - current_100) / 18.0, 0.0)
        elif target_direction == "down":
            delta_score = clamp01((current_100 - target_100) / 18.0, 0.0)
        else:
            delta_score = max(0.0, 1.0 - abs(target_100 - current_100) / 12.0)

        rms_continuity = 1.0 - min(1.0, abs(entry_energy - prev_tail) / max(entry_energy, prev_tail, 0.35))
        drum_strength = clamp01(
            candidate.get("audio_drum_entry_strength", candidate.get("drum_entry_strength", candidate.get("drum_strength"))),
            _drum_entry_strength(song, t, t + fade_sec),
        )
        vocal_sparsity = clamp01(
            candidate.get("audio_vocal_entry_sparsity", candidate.get("vocal_entry_sparsity", candidate.get("vocal_sparsity"))),
            1.0 - _vocal_density(song, t, t + fade_sec),
        )
        melodic_presence = clamp01(
            candidate.get("melodic_presence"),
            _melodic_presence(song, t, t + fade_sec, default=band_density(song)["mid"]),
        )
        handoff_readiness = clamp01(
            candidate.get("handoff_readiness"),
            _handoff_readiness(song, t, t + fade_sec),
        )
        overlap_vocal_conflict = min(prev_vocal, 1.0 - vocal_sparsity)
        anchor_score = 1.0 if candidate.get("anchor") == "downbeat" else 0.75 if candidate.get("anchor") == "beat" else 0.65
        smoothness_score = clamp01(
            0.38 * rms_continuity
            + 0.24 * handoff_readiness
            + 0.18 * drum_strength
            + 0.14 * vocal_sparsity
            + 0.06 * anchor_score,
            0.0,
        )
        beat_alignment_score = anchor_score
        drum_continuity_score = clamp01(0.55 * drum_strength + 0.45 * rms_continuity, 0.0)
        vocal_safety_score = clamp01(vocal_sparsity - overlap_vocal_conflict * 0.5, 0.0)
        score = (
            0.32 * target_match
            + 0.22 * delta_score
            + 0.20 * smoothness_score
            + 0.10 * beat_alignment_score
            + 0.06 * drum_continuity_score
            + 0.04 * vocal_safety_score
            + 0.03 * clamp01(candidate.get("region_score"), 0.5)
            + 0.03 * (1.0 if candidate.get("audio_feature_source") == REQUIRED_AUDIO_FEATURE_SOURCE else 0.35)
        )
        out.append({
            **candidate,
            "time": round(t, 3),
            "score": round(float(score), 4),
            "target_energy_gate_passed": bool(lo <= stable_energy <= hi),
            "target_energy": {
                "target_min": round(float(target_min), 3),
                "target_max": round(float(target_max), 3),
                "target_direction": target_direction,
                "current_reference_energy": round(current_100, 3),
                "target_stable_energy": round(target_100, 3),
                "energy_delta": round(target_100 - current_100, 3),
                "stable_window": [round(stable_start, 3), round(stable_end, 3)],
                "overlap_entry_energy": round(entry_energy * 100.0, 3),
                "in_target": bool(lo <= stable_energy <= hi),
            },
            "breakdown": {
                "target_energy_match": round(target_match, 4),
                "energy_delta_score": round(delta_score, 4),
                "smoothness_score": round(smoothness_score, 4),
                "beat_alignment_score": round(beat_alignment_score, 4),
                "drum_continuity_score": round(drum_continuity_score, 4),
                "vocal_safety_score": round(vocal_safety_score, 4),
                "rms_continuity": round(rms_continuity, 4),
                "drum_strength": round(drum_strength, 4),
                "vocal_sparsity": round(vocal_sparsity, 4),
                "melodic_presence": round(melodic_presence, 4),
                "handoff_readiness": round(handoff_readiness, 4),
                "overlap_vocal_conflict": round(overlap_vocal_conflict, 4),
                "audio_feature_source": candidate.get("audio_feature_source"),
            },
        })
    strict = [item for item in out if item.get("target_energy_gate_passed")]
    if strict:
        return sorted(strict, key=lambda item: (item["score"], item.get("region_score", 0.0)), reverse=True)
    return sorted(out, key=lambda item: (item["score"], item.get("region_score", 0.0)), reverse=True)


def refine_default_transition_alignment(
    prev_song: Any,
    next_song: Any,
    *,
    from_at_sec: float,
    to_at_sec: float,
    fade_sec: float,
    cursor_sec: float = 0.0,
    enforce_min_exit_floor: bool = True,
) -> dict[str, Any]:
    prev_downbeats = _float_list(getattr(prev_song, "downbeats", None))
    next_downbeats = _float_list(getattr(next_song, "downbeats", None))
    prev_beats = _float_list(getattr(prev_song, "beat_points", None))
    next_beats = _float_list(getattr(next_song, "beat_points", None))

    from_refined, from_anchor = _snap_with_anchor(from_at_sec, prev_downbeats, prev_beats, tolerance=1.2)
    to_refined, to_anchor = _snap_with_anchor(to_at_sec, next_downbeats, next_beats, tolerance=1.2)

    min_from = max(20.0, cursor_sec) if enforce_min_exit_floor else max(0.0, cursor_sec)
    if from_refined < min_from:
        from_refined, from_anchor = _first_anchor_after(min_from, prev_downbeats, prev_beats)

    phrase_shift = _phrase_phase_shift(prev_downbeats, next_downbeats, from_refined, to_refined, fade_sec)
    if abs(phrase_shift) > 0.001:
        shifted = to_refined + phrase_shift
        next_duration = float(getattr(next_song, "duration", None) or 0.0)
        upper = min(90.0, next_duration * 0.50) if next_duration > 0 else 90.0
        if 2.0 <= shifted <= upper:
            to_refined, to_anchor = _snap_with_anchor(shifted, next_downbeats, next_beats, tolerance=0.8)

    return {
        "from_at_sec": round(float(from_refined), 3),
        "to_at_sec": round(float(to_refined), 3),
        "from_anchor": from_anchor,
        "to_anchor": to_anchor,
        "phrase_shift_sec": round(float(phrase_shift), 3),
    }


def pair_id_for(
    prev_song: Any,
    next_song: Any,
    from_at: float,
    to_at: float,
    *,
    duration_sec: float = 6.5,
    audio_feature_source: str = "",
) -> str:
    raw = (
        f"{_song_id(prev_song)}__{_song_id(next_song)}__"
        f"{from_at:.3f}__{to_at:.3f}__{duration_sec:.3f}__"
        f"{PLANNER_VERSION}__{REQUIRED_RENDERER_VERSION}__{audio_feature_source or 'unknown'}"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def fast_cut_pair_id_for(
    prev_song: Any,
    next_song: Any,
    requested_exit: float,
    from_at: float,
    to_at: float,
    *,
    duration_sec: float = 6.5,
    audio_feature_source: str = "",
    track2_scan_mode: str | None = None,
) -> str:
    raw = (
        f"fast_cut__{_song_id(prev_song)}__{_song_id(next_song)}__"
        f"{requested_exit:.3f}__{from_at:.3f}__{to_at:.3f}__{duration_sec:.3f}__"
        f"{FAST_CUT_PLANNER_VERSION}__{FAST_CUT_RENDERER_VERSION}__{audio_feature_source or 'unknown'}__"
        f"{track2_scan_mode or 'phrase_change'}"
    )
    return f"fc-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


def target_energy_pair_id_for(
    prev_song: Any,
    next_song: Any,
    from_at: float,
    to_at: float,
    *,
    target_min: float,
    target_max: float,
    duration_sec: float = 6.5,
    audio_feature_source: str = "",
) -> str:
    raw = (
        f"target_energy__{_song_id(prev_song)}__{_song_id(next_song)}__"
        f"{from_at:.3f}__{to_at:.3f}__{duration_sec:.3f}__"
        f"{float(target_min):.3f}__{float(target_max):.3f}__"
        f"{TARGET_ENERGY_PLANNER_VERSION}__{REQUIRED_RENDERER_VERSION}__{audio_feature_source or 'unknown'}"
    )
    return f"te-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


def target_style_pair_id_for(
    prev_song: Any,
    next_song: Any,
    from_at: float,
    to_at: float,
    *,
    target_style: str,
    duration_sec: float = 6.5,
    audio_feature_source: str = "",
) -> str:
    raw = (
        f"target_style__{_song_id(prev_song)}__{_song_id(next_song)}__"
        f"{from_at:.3f}__{to_at:.3f}__{duration_sec:.3f}__"
        f"{str(target_style or '').lower()}__"
        f"{TARGET_STYLE_PLANNER_VERSION}__{REQUIRED_RENDERER_VERSION}__{audio_feature_source or 'unknown'}"
    )
    return f"ts-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


def _default_duration_for_strategy(strategy_num: int) -> float:
    return {1: 6.5, 2: 7.5, 3: 7.0, 4: 6.5, 5: 8.0}.get(int(strategy_num or 1), 6.5)


def _selection_reason(role: str, choice: dict[str, Any]) -> str:
    source = choice.get("source") or "unknown"
    anchor = choice.get("anchor") or "raw"
    score = choice.get("score")
    if score is None:
        return f"{role}: {source}/{anchor}"
    return f"{role}: {source}/{anchor}, score={float(score):.4f}"


def _default_audio_feature_source(exit_choice: dict[str, Any], entry_choice: dict[str, Any]) -> str:
    sources = {
        str(exit_choice.get("audio_feature_source") or ""),
        str(entry_choice.get("audio_feature_source") or ""),
    }
    if sources == {REQUIRED_AUDIO_FEATURE_SOURCE}:
        return REQUIRED_AUDIO_FEATURE_SOURCE
    return "fallback_boundary_or_legacy_features"


def _feature_payload(song: Any, features: dict[str, float]) -> dict[str, Any]:
    return {
        "bpm": features["bpm"],
        "energy": features["energy"],
        "low_ratio": features["low_ratio"],
        "mid_ratio": features["mid_ratio"],
        "high_ratio": features["high_ratio"],
        "music_features": getattr(song, "music_features", None) or {},
        "loudness_profile": getattr(song, "loudness_profile", None) or {},
        "genre_profile": getattr(song, "genre_profile", None) or {},
    }


def _candidate_points_from_regions(
    song: Any,
    *,
    role: str,
    min_time: float,
    max_time: float | None,
    fallback_start: float,
    fallback_end: float | None,
    downbeats: list[float],
    beats: list[float],
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    seen: set[tuple[float, str]] = set()

    def add(t: float, *, source: str, anchor: str, region_score: float = 0.0) -> None:
        if t < min_time:
            return
        if max_time is not None and t > max_time:
            return
        key = (round(float(t), 3), anchor)
        if key in seen:
            return
        seen.add(key)
        points.append({
            "time": round(float(t), 3),
            "source": source,
            "anchor": anchor,
            "region_score": round(float(region_score), 4),
        })

    for region in _transition_regions(song, role=role):
        start = float(region["start"])
        end = float(region["end"])
        region_score = float(region.get("score", 0.5))
        for t in downbeats:
            if start <= t <= end:
                add(t, source=region["source"], anchor="downbeat", region_score=region_score)
        if not any(start <= t <= end for t in downbeats):
            for t in beats:
                if start <= t <= end:
                    add(t, source=region["source"], anchor="beat", region_score=region_score)
        anchor = _nearest(start, downbeats) or _nearest(start, beats)
        if anchor is not None:
            add(anchor, source=region["source"], anchor="nearest_anchor", region_score=region_score)

    if points:
        return sorted(points, key=lambda item: item["time"])

    end = fallback_end if fallback_end is not None else max_time
    if end is not None and end >= fallback_start:
        for t in downbeats:
            if fallback_start <= t <= end:
                add(t, source="beat_bar_fallback", anchor="downbeat", region_score=0.35)
        if not points:
            for t in beats:
                if fallback_start <= t <= end:
                    add(t, source="beat_bar_fallback", anchor="beat", region_score=0.25)

    return sorted(points, key=lambda item: item["time"])


def _dj_structure(song: Any) -> dict[str, Any]:
    music_features = getattr(song, "music_features", None) or {}
    if not isinstance(music_features, dict):
        return {}
    for key in ("dj_structure_v2", "dj_structure_v1"):
        structure = music_features.get(key)
        if isinstance(structure, dict):
            if structure.get("version"):
                return structure
            return {**structure, "version": key}
    return {}


def _candidate_points_from_dj_structure(
    song: Any,
    *,
    role: str,
    min_time: float,
    max_time: float | None,
) -> list[dict[str, Any]]:
    structure = _dj_structure(song)
    key = "track1_exit_candidates" if role == "exit" else "track2_entry_candidates"
    version = str(structure.get("version") or "dj_structure")
    raw_candidates = structure.get(key)
    if not isinstance(raw_candidates, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[float] = set()
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        t = _float(raw.get("time"), None)
        if t is None or t < min_time:
            continue
        if max_time is not None and t > max_time:
            continue
        rounded = round(float(t), 3)
        if rounded in seen:
            continue
        seen.add(rounded)
        score = _first_numeric_field(raw, ("score", "entry_score", "mix_in_score", "mix_out_score"), default=0.5)
        candidate = {
            "time": rounded,
            "source": f"{version}.{key}",
            "anchor": "structure_boundary",
            "region_score": round(float(score), 4),
            "dj_structure_v1": _compact_structure_candidate(raw),
        }
        for field in (
            "local_rms",
            "entry_rms",
            "stable_section_energy",
            "target_stable_energy",
            "post_handoff_energy",
            "post_handoff_rms",
            "local_energy",
            "window_energy",
            "section_energy",
            "energy",
            "tail_rms",
            "vocal_sparsity",
            "vocal_entry_sparsity",
            "drum_strength",
            "drum_stability",
            "drum_entry_strength",
            "immediate_punch",
            "immediate_entry_punch",
            "melodic_presence",
            "fullness",
            "fullness_score",
            "handoff_readiness",
            "tail_energy_score",
            "low_ratio",
            "mid_ratio",
            "high_ratio",
            "audio_feature_source",
        ):
            if field in raw:
                candidate[field] = raw.get(field)
        if role == "entry":
            candidate["entry_score"] = round(float(_first_numeric_field(raw, ("entry_score", "score"), default=score)), 4)
        out.append(candidate)
    return sorted(out, key=lambda item: (item["region_score"], item["time"]), reverse=True)[:64]


def _fast_cut_v2_exit_points(
    song: Any,
    *,
    min_time: float,
    max_time: float | None,
    inclusive_min: bool = True,
) -> list[dict[str, Any]]:
    """Return only stored v2 exit candidates for a manual fast cut."""
    structure = _dj_structure(song)
    if str(structure.get("version") or "") != "dj_structure_v2":
        return []
    points = _candidate_points_from_dj_structure(
        song,
        role="exit",
        min_time=min_time,
        max_time=max_time,
    )
    out = []
    for point in points:
        if not inclusive_min and float(point["time"]) <= min_time:
            continue
        if point.get("audio_feature_source") != REQUIRED_AUDIO_FEATURE_SOURCE:
            continue
        out.append(point)
    return out


def _fast_cut_boundary_candidates(
    song: Any,
    *,
    scan_mode: str,
    min_time: float,
    max_time: float,
) -> list[dict[str, Any]]:
    mode = scan_mode or "phrase_change"
    mode_keys = {
        "phrase_change": (
            "phrase_change_boundaries",
            "phrase_change_points",
            "phrase_changes",
            "structure_change_boundaries",
        ),
        "phrase": ("phrase_boundaries", "phrase_anchors", "phrase_points"),
        "bar": ("bar_boundaries", "bar_points"),
        "beat": ("beat_boundaries", "beat_points"),
    }
    priority = [
        mode,
        "phrase_change",
        "phrase",
        "bar",
        "beat",
    ]
    structure = _dj_structure(song)
    out: list[dict[str, Any]] = []
    seen: set[float] = set()

    def add_many(values: Any, *, source: str, anchor: str, score: float) -> None:
        for t in _float_list(values):
            if t < min_time or t > max_time:
                continue
            rounded = round(float(t), 3)
            if rounded in seen:
                continue
            seen.add(rounded)
            out.append({
                "time": rounded,
                "source": source,
                "anchor": anchor,
                "region_score": round(float(score), 4),
            })

    for current_mode in dict.fromkeys(priority):
        keys = mode_keys.get(current_mode)
        if not keys:
            continue
        for key in keys:
            add_many(
                structure.get(key),
                source=f"fast_cut.dj_structure_v1.{key}",
                anchor=current_mode,
                score={
                    "phrase_change": 0.78,
                    "phrase": 0.66,
                    "bar": 0.48,
                    "beat": 0.32,
                }.get(current_mode, 0.35),
            )

    add_many(getattr(song, "downbeats", None), source="fast_cut.downbeats", anchor="downbeat", score=0.42)
    add_many(getattr(song, "beat_points", None), source="fast_cut.beat_points", anchor="beat", score=0.28)
    return _dedupe_candidate_times(out, max_points=64)


def _dense_boundary_candidates(
    song: Any,
    *,
    role: str,
    min_time: float,
    max_time: float | None,
    source_prefix: str,
) -> list[dict[str, Any]]:
    """Build a bounded candidate pool like the standalone module's boundary scan.

    The standalone quick-transition script scans phrase/bar/beat anchors before
    scoring.  In production we reuse persisted boundaries instead of decoding
    audio at request time, but preserve the same "scan then score" shape.
    """
    structure = _dj_structure(song)
    upper = max_time if max_time is not None else float("inf")
    out: list[dict[str, Any]] = []
    seen: set[float] = set()

    def add_many(values: Any, *, source: str, anchor: str, score: float) -> None:
        for t in _float_list(values):
            if t < min_time or t > upper:
                continue
            rounded = round(float(t), 3)
            if rounded in seen:
                continue
            seen.add(rounded)
            out.append({
                "time": rounded,
                "source": source,
                "anchor": anchor,
                "region_score": round(float(score), 4),
            })

    role_bias = 0.02 if role == "entry" else 0.0
    add_many(
        structure.get("phrase_change_boundaries")
        or structure.get("phrase_change_points")
        or structure.get("phrase_changes")
        or structure.get("structure_change_boundaries"),
        source=f"{source_prefix}.dj_structure_v1.phrase_change_boundaries",
        anchor="phrase_change",
        score=0.78 + role_bias,
    )
    add_many(
        structure.get("phrase_boundaries")
        or structure.get("phrase_anchors")
        or structure.get("phrase_points"),
        source=f"{source_prefix}.dj_structure_v1.phrase_boundaries",
        anchor="phrase",
        score=0.66 + role_bias,
    )
    add_many(
        structure.get("bar_boundaries") or structure.get("bar_points"),
        source=f"{source_prefix}.dj_structure_v1.bar_boundaries",
        anchor="bar",
        score=0.48 + role_bias,
    )
    add_many(
        structure.get("beat_boundaries") or structure.get("beat_points"),
        source=f"{source_prefix}.dj_structure_v1.beat_boundaries",
        anchor="beat",
        score=0.32,
    )
    add_many(getattr(song, "downbeats", None), source=f"{source_prefix}.downbeats", anchor="downbeat", score=0.42)
    add_many(getattr(song, "beat_points", None), source=f"{source_prefix}.beat_points", anchor="beat", score=0.28)
    return _dedupe_candidate_times(out, max_points=64)


def _dedupe_candidate_times(candidates: list[dict[str, Any]], *, max_points: int = 64) -> list[dict[str, Any]]:
    by_time: dict[float, dict[str, Any]] = {}
    for item in candidates:
        try:
            rounded = round(float(item.get("time")), 3)
        except (TypeError, ValueError):
            continue
        prev = by_time.get(rounded)
        item_has_audio = bool(item.get("audio_feature_source"))
        prev_has_audio = bool(prev.get("audio_feature_source")) if prev else False
        if (
            prev is None
            or (item_has_audio and not prev_has_audio)
            or (
                item_has_audio == prev_has_audio
                and float(item.get("region_score", 0.0) or 0.0) > float(prev.get("region_score", 0.0) or 0.0)
            )
        ):
            by_time[rounded] = {**item, "time": rounded}
    ordered = sorted(by_time.values(), key=lambda item: (float(item.get("region_score", 0.0) or 0.0), -float(item["time"])), reverse=True)
    limited = ordered[:max_points]
    return sorted(limited, key=lambda item: float(item["time"]))


def _annotate_entry_candidates_with_audio(
    song: Any,
    candidates: list[dict[str, Any]],
    *,
    prev_song: Any,
    from_at_sec: float,
    fade_sec: float,
) -> list[dict[str, Any]]:
    if os.environ.get("HARBEAT_DEFAULT_MIX_RUNTIME_AUDIO_SCAN", "").strip().lower() not in {"1", "true", "yes"}:
        return candidates
    if not candidates:
        return candidates
    path = Path(str(getattr(song, "source_path", "") or ""))
    if not path.is_file():
        return candidates
    try:
        import librosa
        import numpy as np
    except Exception:
        return candidates
    try:
        audio, sr = librosa.load(str(path), sr=44100, mono=True)
    except Exception:
        return candidates
    prev_tail_rms = _audio_tail_rms(prev_song, from_at_sec=from_at_sec, fade_sec=fade_sec)
    out: list[dict[str, Any]] = []
    for candidate in candidates:
        t = _float(candidate.get("time"), None)
        if t is None:
            out.append(candidate)
            continue
        segment = _audio_window(audio, sr, t, fade_sec)
        if len(segment) < 2048:
            out.append(candidate)
            continue
        early = _audio_window(audio, sr, t, min(2.0, fade_sec))
        punch = _audio_window(audio, sr, t, 0.8)
        try:
            percussive = librosa.effects.percussive(segment)
            early_percussive = librosa.effects.percussive(early) if len(early) >= 1024 else percussive
            punch_percussive = librosa.effects.percussive(punch) if len(punch) >= 1024 else early_percussive
            onset_env = librosa.onset.onset_strength(y=percussive, sr=sr)
            early_onset_env = librosa.onset.onset_strength(y=early_percussive, sr=sr)
            punch_onset_env = librosa.onset.onset_strength(y=punch_percussive, sr=sr)
        except Exception:
            onset_env = np.asarray([], dtype=np.float32)
            early_onset_env = np.asarray([], dtype=np.float32)
            punch_onset_env = np.asarray([], dtype=np.float32)

        stft = np.abs(librosa.stft(segment))
        freqs = librosa.fft_frequencies(sr=sr)
        total = float(np.sum(stft)) + 1e-10
        low_ratio = float(np.sum(stft[freqs < 220, :]) / total)
        mid_ratio = float(np.sum(stft[(freqs >= 250) & (freqs < 4000), :]) / total)
        entry_rms = _array_rms(segment)
        full_rms = max(entry_rms, 1e-10)
        perc_rms = _array_rms(percussive) if len(percussive) else 0.0
        early_full_rms = max(_array_rms(early), 1e-10)
        early_perc_rms = _array_rms(early_percussive) if len(early_percussive) else 0.0
        onset_score = float(np.clip(np.mean(onset_env) / 6.0, 0.0, 1.0)) if onset_env.size else 0.0
        early_onset_score = float(np.clip(np.mean(early_onset_env) / 6.5, 0.0, 1.0)) if early_onset_env.size else 0.0
        attack_score = float(np.clip(np.max(early_onset_env) / 12.0, 0.0, 1.0)) if early_onset_env.size else 0.0
        punch_peak = float(np.clip(np.max(punch_onset_env) / 14.0, 0.0, 1.0)) if punch_onset_env.size else 0.0
        punch_mean = float(np.clip(np.mean(punch_onset_env) / 7.0, 0.0, 1.0)) if punch_onset_env.size else 0.0
        drum_strength = float(np.clip(
            0.18 * onset_score
            + 0.12 * np.clip(low_ratio / 0.38, 0.0, 1.0)
            + 0.10 * np.clip(perc_rms / full_rms / 0.95, 0.0, 1.0)
            + 0.22 * early_onset_score
            + 0.18 * attack_score
            + 0.10 * np.clip(low_ratio / 0.40, 0.0, 1.0)
            + 0.10 * np.clip(early_perc_rms / early_full_rms / 0.95, 0.0, 1.0),
            0.0,
            1.0,
        ))
        immediate_punch = float(np.clip(
            0.35 * punch_peak
            + 0.20 * punch_mean
            + 0.25 * np.clip(low_ratio / 0.42, 0.0, 1.0)
            + 0.20 * np.clip(early_perc_rms / early_full_rms / 0.95, 0.0, 1.0),
            0.0,
            1.0,
        ))
        out.append({
            **candidate,
            "audio_feature_source": "librosa_window",
            "audio_entry_rms": round(float(entry_rms), 6),
            "audio_prev_tail_rms": round(float(prev_tail_rms), 6) if prev_tail_rms is not None else None,
            "audio_drum_entry_strength": round(drum_strength, 4),
            "audio_immediate_entry_punch": round(immediate_punch, 4),
            "audio_vocal_entry_sparsity": round(float(np.clip(1.0 - mid_ratio, 0.0, 1.0)), 4),
        })
    return out


def _audio_tail_rms(song: Any, *, from_at_sec: float, fade_sec: float) -> float | None:
    path = Path(str(getattr(song, "source_path", "") or ""))
    if not path.is_file():
        return None
    try:
        import librosa
    except Exception:
        return None
    try:
        audio, sr = librosa.load(str(path), sr=44100, mono=True)
    except Exception:
        return None
    start = max(0.0, float(from_at_sec) - float(fade_sec))
    segment = _audio_window(audio, sr, start, fade_sec)
    if len(segment) == 0:
        return None
    return _array_rms(segment)


def _audio_window(audio: Any, sr: int, start_sec: float, duration_sec: float) -> Any:
    start = max(0, int(round(float(start_sec) * sr)))
    end = min(len(audio), int(round((float(start_sec) + float(duration_sec)) * sr)))
    return audio[start:end]


def _array_rms(audio: Any) -> float:
    if len(audio) == 0:
        return 0.0
    try:
        import numpy as np
    except Exception:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))


def _compact_structure_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "type",
        "score",
        "entry_score",
        "local_rms",
        "structure_change_score",
        "vocal_sparsity",
        "vocal_entry_sparsity",
        "drum_strength",
        "drum_stability",
        "drum_entry_strength",
        "immediate_punch",
        "immediate_entry_punch",
        "melodic_presence",
        "fullness",
        "fullness_score",
        "handoff_readiness",
        "tail_energy_score",
        "tail_rms",
        "entry_rms",
        "low_ratio",
        "mid_ratio",
        "high_ratio",
        "audio_feature_source",
        "reason",
    )
    return {key: raw.get(key) for key in keys if key in raw}


def _entry_fallback_lower_bound(duration: float, upper: float) -> float:
    if upper <= 2.0:
        return 2.0
    if duration <= 0:
        return 8.0
    return min(upper, max(5.0, min(16.0, duration * 0.08)))


def _entry_safety_fallback_points(
    *,
    min_time: float,
    max_time: float,
    downbeats: list[float],
    beats: list[float],
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for grid, anchor, score in ((downbeats, "downbeat", 0.28), (beats, "beat", 0.20)):
        for t in grid:
            if min_time <= t <= max_time:
                points.append({
                    "time": round(float(t), 3),
                    "source": "beat_bar_safety_fallback",
                    "anchor": anchor,
                    "region_score": score,
                })
        if points:
            return points[:64]
    if max_time >= min_time:
        return [{
            "time": round(float(min_time), 3),
            "source": "duration_entry_safety_fallback",
            "anchor": "raw",
            "region_score": 0.10,
        }]
    return []


def _candidate_has_zero_source_score(candidate: dict[str, Any]) -> bool:
    source = str(candidate.get("source") or "")
    if source not in {"transition_windows", "stem_transition_windows"}:
        return False
    try:
        return float(candidate.get("region_score", 0.0)) <= 0.0
    except (TypeError, ValueError):
        return False


def _relaxed_entry_candidate_allowed(candidate: dict[str, Any]) -> bool:
    failures = set(candidate.get("entry_gate_failures") or [])
    if "source_entry_score_zero" in failures or "zero_entry_quality_metrics" in failures:
        return False
    if candidate.get("source") in {"zero_fallback", "no_usable_entry_fallback"}:
        return False
    try:
        score = float(candidate.get("score", 0.0))
    except (TypeError, ValueError):
        return False
    return score > 0.25


def _source_candidate_score(candidate: dict[str, Any]) -> float:
    try:
        return float(candidate.get("region_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _transition_regions(song: Any, *, role: str) -> list[dict[str, Any]]:
    duration = float(getattr(song, "duration", None) or 0.0)
    out: list[dict[str, Any]] = []
    windows = getattr(song, "transition_windows", None) or []
    for item in windows:
        if not isinstance(item, dict):
            continue
        raw_start = (
            item.get("entry_start_sec")
            if role == "entry" and item.get("entry_start_sec") is not None
            else item.get("start", item.get("time", item.get("start_sec")))
        )
        try:
            start = float(raw_start)
        except (TypeError, ValueError):
            continue
        try:
            end = float(item.get("end", item.get("end_sec", start + 8.0)))
        except (TypeError, ValueError):
            end = start + 8.0
        if role == "entry":
            start = max(2.0, start - 1.5)
            end = max(start + 0.5, min(end + 2.0, 90.0, duration * 0.50 if duration > 0 else 90.0))
            score = _first_numeric_field(
                item,
                ("entry_score", "mix_in_score", "mix_score", "score", "priority"),
                default=0.5,
            )
        else:
            start = max(0.0, start - 2.0)
            end = max(start + 0.5, end + 1.5)
            score = _first_numeric_field(
                item,
                ("mix_out_score", "mix_score", "score", "priority"),
                default=0.5,
            )
        out.append({
            "start": start,
            "end": end,
            "score": clamp01(score, 0.5),
            "source": "stem_transition_windows" if getattr(song, "stem_activity_windows", None) else "transition_windows",
        })

    if out:
        return sorted(out, key=lambda item: item["score"], reverse=True)[:8]

    phrases = getattr(song, "phrase_map", None) or []
    if isinstance(phrases, list):
        if role == "entry":
            candidates = phrases[:5]
        else:
            candidates = phrases[-5:]
        for phrase in candidates:
            if not isinstance(phrase, dict):
                continue
            try:
                start = float(phrase.get("start", phrase.get("start_sec", 0.0)))
                end = float(phrase.get("end", phrase.get("end_sec", start + 16.0)))
            except (TypeError, ValueError):
                continue
            if role == "entry":
                if duration > 0 and start > min(90.0, duration * 0.50):
                    continue
                score = 0.45 if start < 32.0 else 0.30
            else:
                if duration > 0 and end < duration * 0.55:
                    continue
                score = 0.45 if duration <= 0 or start >= duration * 0.70 else 0.32
            out.append({"start": start, "end": end, "score": score, "source": "phrase_map"})
    return out


def _first_numeric_field(item: dict[str, Any], keys: tuple[str, ...], *, default: float) -> float:
    for key in keys:
        if key not in item or item.get(key) is None:
            continue
        try:
            return float(item.get(key))
        except (TypeError, ValueError):
            continue
    return float(default)


def _energy_in_range(song: Any, start: float, end: float) -> float:
    curve = getattr(song, "energy_curve", None) or []
    if not isinstance(curve, list) or not curve or end <= start:
        return clamp01(getattr(song, "energy", None), 0.5)
    values: list[float] = []
    for item in curve:
        if isinstance(item, dict):
            t = _float(item.get("time", item.get("sec", item.get("start"))), None)
            val = item.get("energy", item.get("value", item.get("score")))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            t = _float(item[0], None)
            val = item[1]
        else:
            continue
        if t is not None and start <= t <= end:
            values.append(clamp01(val, 0.5))
    return sum(values) / len(values) if values else clamp01(getattr(song, "energy", None), 0.5)


def _energy_100_to_unit(value: float) -> float:
    raw = _float(value, 50.0)
    if raw is None:
        raw = 50.0
    if raw > 1.0:
        raw /= 100.0
    return clamp01(raw, 0.5)


def _candidate_energy_unit(value: Any, default: float) -> float:
    raw = _float(value, None)
    if raw is None:
        return clamp01(default, 0.5)
    if raw > 1.0:
        raw /= 100.0
    return clamp01(raw, default)


def _energy_bucket_match_unit(score: float, lo: float, hi: float) -> float:
    score = clamp01(score, 0.5)
    lo = clamp01(lo, 0.0)
    hi = clamp01(hi, 1.0)
    if hi < lo:
        lo, hi = hi, lo
    if lo <= score <= hi:
        center = (lo + hi) * 0.5
        half = max(0.01, (hi - lo) * 0.5)
        return max(0.75, 1.0 - abs(score - center) / (half * 2.0))
    if score < lo:
        return max(0.0, 1.0 - (lo - score) / 0.30)
    return max(0.0, 1.0 - (score - hi) / 0.30)


def _candidate_entry_energy(song: Any, candidate: dict[str, Any], start: float, end: float) -> float:
    for key in ("entry_rms", "local_rms", "local_energy", "window_energy", "energy"):
        if key in candidate:
            return _candidate_energy_unit(candidate.get(key), _energy_in_range(song, start, end))
    return _energy_in_range(song, start, end)


def _candidate_stable_energy(song: Any, candidate: dict[str, Any], start: float, end: float) -> float:
    for key in (
        "target_stable_energy",
        "stable_section_energy",
        "post_handoff_energy",
        "section_energy",
        "local_energy",
        "energy",
    ):
        if key in candidate:
            return _candidate_energy_unit(candidate.get(key), _energy_in_range(song, start, end))
    return _energy_in_range(song, start, end)


def _vocal_density(song: Any, start: float, end: float) -> float:
    events = getattr(song, "vocal_events", None) or []
    if not events:
        return clamp01((getattr(song, "genre_profile", None) or {}).get("vocal_density"), 0.35)
    return clamp01(vocal_density_in_range(events, start, end), 0.35)


def _drum_stability(song: Any, start: float, end: float) -> float:
    stems = _stem_values_in_range(song, start, end)
    if stems:
        drums = stems.get("drums")
        if drums is not None:
            return clamp01(drums, 0.55)
    beats = [t for t in _float_list(getattr(song, "beat_points", None)) if start <= t <= end]
    if len(beats) < 3:
        return 0.45
    gaps = [beats[i + 1] - beats[i] for i in range(len(beats) - 1)]
    avg = sum(gaps) / len(gaps)
    if avg <= 0:
        return 0.45
    variance = sum(abs(g - avg) for g in gaps) / len(gaps)
    return max(0.0, min(1.0, 1.0 - variance / max(0.001, avg)))


def _drum_entry_strength(song: Any, start: float, end: float) -> float:
    stems = _stem_values_in_range(song, start, min(end, start + 3.0))
    if stems and stems.get("drums") is not None:
        return clamp01(stems.get("drums"), 0.55)
    downbeats = [t for t in _float_list(getattr(song, "downbeats", None)) if start - 0.25 <= t <= min(end, start + 4.0)]
    beats = [t for t in _float_list(getattr(song, "beat_points", None)) if start <= t <= min(end, start + 4.0)]
    return clamp01(0.35 + 0.18 * len(downbeats) + 0.04 * len(beats), 0.45)


def _melodic_presence(song: Any, start: float, end: float, *, default: float) -> float:
    stems = _stem_values_in_range(song, start, end)
    if stems:
        vals = [stems[k] for k in ("vocals", "other", "piano", "guitar") if k in stems]
        if vals:
            return clamp01(sum(vals) / len(vals), default)
    return clamp01(default, 0.5)


def _handoff_readiness(song: Any, start: float, end: float) -> float:
    vocal = _vocal_density(song, start, end)
    drums = _drum_stability(song, start, end)
    bass = band_density(song)["low"]
    energy = _energy_in_range(song, start, end)
    return clamp01(0.35 * (1.0 - vocal) + 0.30 * drums + 0.20 * energy + 0.15 * bass, 0.5)


def _stem_values_in_range(song: Any, start: float, end: float) -> dict[str, float]:
    windows = getattr(song, "stem_activity_windows", None) or []
    if not isinstance(windows, list) or end <= start:
        return {}
    accum: dict[str, float] = {}
    total = 0.0
    for item in windows:
        if not isinstance(item, dict):
            continue
        w_start = _float(item.get("start", item.get("time")), 0.0)
        w_end = _float(item.get("end"), w_start + _float(item.get("duration"), 0.0))
        overlap = max(0.0, min(end, w_end) - max(start, w_start))
        if overlap <= 0:
            continue
        total += overlap
        for key, val in item.items():
            if key in {"start", "end", "time", "duration"}:
                continue
            try:
                accum[key] = accum.get(key, 0.0) + float(val) * overlap
            except (TypeError, ValueError):
                continue
    if total <= 0:
        return {}
    return {key: clamp01(value / total, 0.0) for key, value in accum.items()}


def _snap_with_anchor(target: float, downbeats: list[float], beats: list[float], *, tolerance: float) -> tuple[float, str]:
    downbeat = _nearest(target, downbeats)
    if downbeat is not None and abs(downbeat - target) <= tolerance:
        return downbeat, "downbeat"
    beat = _nearest(target, beats)
    if beat is not None and abs(beat - target) <= tolerance:
        return beat, "beat"
    return target, "raw"


def _first_anchor_after(target: float, downbeats: list[float], beats: list[float]) -> tuple[float, str]:
    for grid, label in ((downbeats, "downbeat"), (beats, "beat")):
        for t in grid:
            if t >= target:
                return t, label
    return target, "raw"


def _phrase_phase_shift(
    prev_downbeats: list[float],
    next_downbeats: list[float],
    from_at: float,
    to_at: float,
    fade_sec: float,
) -> float:
    if len(prev_downbeats) < 3 or len(next_downbeats) < 3:
        return 0.0
    prev_idx = _nearest_index(from_at, prev_downbeats)
    next_idx = _nearest_index(to_at, next_downbeats)
    if prev_idx is None or next_idx is None:
        return 0.0
    target_phase = prev_idx % 4
    next_phase = next_idx % 4
    delta_bars = (target_phase - next_phase) % 4
    if delta_bars == 0:
        return 0.0
    if delta_bars > 2:
        delta_bars -= 4
    step = _median_interval(next_downbeats) or max(1.0, fade_sec / 4.0)
    shift = delta_bars * step
    max_shift = min(2.0, max(0.5, fade_sec * 0.25))
    return max(-max_shift, min(max_shift, shift))


def _nearest(target: float, points: list[float]) -> float | None:
    if not points:
        return None
    return min(points, key=lambda t: abs(t - target))


def _nearest_index(target: float, points: list[float]) -> int | None:
    if not points:
        return None
    return min(range(len(points)), key=lambda idx: abs(points[idx] - target))


def _median_interval(points: list[float]) -> float | None:
    if len(points) < 2:
        return None
    gaps = sorted(points[i + 1] - points[i] for i in range(len(points) - 1) if points[i + 1] > points[i])
    if not gaps:
        return None
    return gaps[len(gaps) // 2]


def _float_list(raw: Any) -> list[float]:
    if not isinstance(raw, list):
        return []
    out: list[float] = []
    for item in raw:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            if isinstance(item, dict):
                val = item.get("time") or item.get("start") or item.get("t")
                try:
                    out.append(float(val))
                except (TypeError, ValueError):
                    pass
    return sorted(t for t in out if t >= 0.0)


def _float(value: Any, default: Any) -> Any:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _song_id(song: Any) -> str:
    return str(getattr(song, "id", "") or getattr(song, "song_id", ""))


