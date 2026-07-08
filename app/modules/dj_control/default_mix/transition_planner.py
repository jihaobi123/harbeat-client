"""Default transition planner.

This module ports the current offline default-mix strategy into a fast runtime
planner.  It prefers persisted stem/beat analysis when present and falls back
to beat/bar metadata from MP3 analysis.  It can also wrap the default metadata
inside a section_match-compatible EQ plan for phase-0 mobile compatibility.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.modules.dj_control import eq_transition_strategy
from app.modules.dj_control.band_analysis import band_density, clamp01, curve_average
from app.modules.dj_control.auto_mixer.feature_analyzer import FeatureAnalyzer
from app.modules.dj_control.auto_mixer.strategy_selector import StrategySelector
from app.modules.dj_control.spotify_mix.section_features import vocal_density_in_range


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
    pair_id = pair_id_for(prev_song, next_song, from_at, to_at)
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
            "fallback": "beat/downbeat/bar metadata from MP3 analysis",
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


def attach_render_resources(
    plan: dict[str, Any],
    *,
    render_meta: dict[str, Any],
    base_url: str = "",
) -> dict[str, Any]:
    """Attach default render paths and URLs to a default plan.

    The sync-worker consumes the ``transition_render_url`` and pair manifest
    entries.  The RK audio engine consumes ``pair_id`` and local cache paths.
    """
    from app.modules.dj_control.default_mix import reference_renderer

    out = dict(plan)
    default_meta = dict(out.get("default_mix") or {})
    pair_id = str(out.get("pair_id") or default_meta.get("pair_id") or render_meta.get("pair_id") or "")
    render_path = render_meta.get("transition_render_path")
    render_meta_path = render_meta.get("transition_render_meta_path")
    if render_path:
        out["transition_render_path"] = str(render_path)
        default_meta["transition_render_path"] = str(render_path)
    if render_meta_path:
        out["transition_render_meta_path"] = str(render_meta_path)
        default_meta["transition_render_meta_path"] = str(render_meta_path)
    out["pair_id"] = pair_id
    default_meta["pair_id"] = pair_id
    default_meta["resume_at_sec"] = render_meta.get("resume_at_sec", default_meta.get("resume_at_sec"))
    default_meta["duration_sec"] = render_meta.get("duration_sec", default_meta.get("duration_sec"))
    default_meta["energy_match_gain_db"] = render_meta.get(
        "energy_match_gain_db",
        default_meta.get("energy_match_gain_db"),
    )
    out["resume_at_sec"] = default_meta.get("resume_at_sec")
    out["duration_sec"] = default_meta.get("duration_sec", out.get("duration_sec"))
    out["fade_sec"] = out.get("duration_sec")

    if pair_id:
        route = f"/api/dj/default/render/{pair_id}"
        meta_route = f"/api/dj/default/render/{pair_id}/meta"
        out["transition_render_url"] = f"{base_url.rstrip('/')}{route}" if base_url else route
        out["transition_render_meta_url"] = f"{base_url.rstrip('/')}{meta_route}" if base_url else meta_route
        out["default_mix_pair_manifest"] = {
            "pair_id": pair_id,
            "files": {
                "transition_render": {
                    "url": out["transition_render_url"],
                    "format": "wav",
                    "size": _path_size(render_path),
                },
                "transition_render_meta": {
                    "url": out["transition_render_meta_url"],
                    "format": "json",
                    "size": _path_size(render_meta_path),
                },
            },
        }
        default_meta["rk_cache_render_path"] = str(
            Path("~/cypher/cache/default-mix/pairs").expanduser() / pair_id / "transition_render.wav"
        )
    out["default_mix"] = default_meta
    return out


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
    points = _candidate_points_from_regions(
        next_song,
        role="entry",
        min_time=2.0,
        max_time=upper,
        fallback_start=2.0,
        fallback_end=upper,
        downbeats=downbeats,
        beats=beats,
    )
    prev_tail_energy = _energy_in_range(prev_song, from_at_sec, from_at_sec + fade_sec)
    scored = score_entry_candidates(
        next_song,
        points,
        prev_tail_energy=prev_tail_energy,
        prev_vocal_events=getattr(prev_song, "vocal_events", None) or [],
        fade_sec=fade_sec,
    )
    if scored:
        return scored[0]
    return {
        "time": 0.0,
        "score": 0.0,
        "source": "zero_fallback",
        "breakdown": {},
    }


def exit_source(song: Any) -> str:
    return "stem_transition_windows" if getattr(song, "transition_windows", None) else "beat_bar"


def entry_source(song: Any) -> str:
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
        vocal_density = _vocal_density(song, t, end)
        vocal_sparsity = 1.0 - vocal_density
        drum_stability = _drum_stability(song, t, end)
        melodic_presence = _melodic_presence(song, t, end, default=bands["mid"])
        fullness_score = _energy_in_range(song, max(0.0, t - 2.0), end)
        tail_energy_score = _energy_in_range(song, window_start, end)
        handoff_readiness = _handoff_readiness(song, t, end)
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
        entry_energy = _energy_in_range(song, t, end)
        energy_match_score = 1.0 - min(1.0, abs(entry_energy - prev_tail_energy) / 0.55)
        drum_entry_strength = _drum_entry_strength(song, t, end)
        immediate_entry_punch = _energy_in_range(song, t, min(end, t + 2.0))
        vocal_density = _vocal_density(song, t, end)
        vocal_entry_sparsity = 1.0 - vocal_density
        prev_vocal = vocal_density_in_range(prev_vocal_events, 0.0, fade_sec)
        overlap_vocal_conflict = min(prev_vocal, vocal_density)
        anchor_bonus = 0.05 if candidate.get("anchor") == "downbeat" else 0.02
        early_score = 1.0 - min(1.0, max(0.0, t - 24.0) / 66.0)
        score = (
            0.28 * energy_match_score
            + 0.22 * drum_entry_strength
            + 0.16 * immediate_entry_punch
            + 0.18 * vocal_entry_sparsity
            + 0.10 * early_score
            - 0.22 * overlap_vocal_conflict
            + anchor_bonus
        )
        out.append({
            **candidate,
            "time": round(t, 3),
            "score": round(float(score), 4),
            "breakdown": {
                "energy_match_score": round(energy_match_score, 4),
                "drum_entry_strength": round(drum_entry_strength, 4),
                "immediate_entry_punch": round(immediate_entry_punch, 4),
                "vocal_entry_sparsity": round(vocal_entry_sparsity, 4),
                "overlap_vocal_conflict": round(overlap_vocal_conflict, 4),
                "early_score": round(early_score, 4),
                "anchor_bonus": round(anchor_bonus, 4),
            },
        })
    return sorted(out, key=lambda item: (item["score"], item.get("region_score", 0.0)), reverse=True)


def refine_default_transition_alignment(
    prev_song: Any,
    next_song: Any,
    *,
    from_at_sec: float,
    to_at_sec: float,
    fade_sec: float,
    cursor_sec: float = 0.0,
) -> dict[str, Any]:
    prev_downbeats = _float_list(getattr(prev_song, "downbeats", None))
    next_downbeats = _float_list(getattr(next_song, "downbeats", None))
    prev_beats = _float_list(getattr(prev_song, "beat_points", None))
    next_beats = _float_list(getattr(next_song, "beat_points", None))

    from_refined, from_anchor = _snap_with_anchor(from_at_sec, prev_downbeats, prev_beats, tolerance=1.2)
    to_refined, to_anchor = _snap_with_anchor(to_at_sec, next_downbeats, next_beats, tolerance=1.2)

    if from_refined < max(20.0, cursor_sec):
        from_refined, from_anchor = _first_anchor_after(max(20.0, cursor_sec), prev_downbeats, prev_beats)

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


def pair_id_for(prev_song: Any, next_song: Any, from_at: float, to_at: float) -> str:
    raw = f"{_song_id(prev_song)}__{_song_id(next_song)}__{from_at:.3f}__{to_at:.3f}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _default_duration_for_strategy(strategy_num: int) -> float:
    return {1: 6.5, 2: 7.5, 3: 7.0, 4: 6.5, 5: 8.0}.get(int(strategy_num or 1), 6.5)


def _selection_reason(role: str, choice: dict[str, Any]) -> str:
    source = choice.get("source") or "unknown"
    anchor = choice.get("anchor") or "raw"
    score = choice.get("score")
    if score is None:
        return f"{role}: {source}/{anchor}"
    return f"{role}: {source}/{anchor}, score={float(score):.4f}"


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
            score = item.get("entry_score") or item.get("mix_in_score") or item.get("mix_score") or item.get("score") or item.get("priority") or 0.5
        else:
            start = max(0.0, start - 2.0)
            end = max(start + 0.5, end + 1.5)
            score = item.get("mix_out_score") or item.get("mix_score") or item.get("score") or item.get("priority") or 0.5
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


def _path_size(path: Any) -> int | None:
    if not path:
        return None
    try:
        from pathlib import Path

        return Path(str(path)).stat().st_size
    except OSError:
        return None
