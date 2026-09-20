"""Section-matching transition planner for local Spotify-style mixing."""

from __future__ import annotations

import logging
from typing import Any

from app.modules.dj_control.auto_mixer.feature_analyzer import FeatureAnalyzer, get_song_file_path
from app.modules.dj_control.auto_mixer.mixing_strategies import MixingStrategyParams
from app.modules.dj_control.auto_mixer.strategy_selector import StrategySelector
from app.modules.dj_control.eq_transition_strategy import generate_eq_band_mix_transition
from app.modules.dj_control.spotify_mix.beat_bar_points import build_transition_point_candidates
from app.modules.dj_control.spotify_mix.camelot_distance import camelot_distance
from app.modules.dj_control.spotify_mix.section_features import (
    enumerate_intro_sections,
    enumerate_outro_sections,
    vocal_density_in_range,
)
from app.modules.dj_control.spotify_mix.section_scorer import (
    quality_tier,
    score_section_pair,
)

V32_MIN_FADE_SEC = 6.0
logger = logging.getLogger(__name__)


def plan_section_match_transition(
    song_a: dict[str, Any],
    song_b: dict[str, Any],
    *,
    cursor_sec: float | None = None,
    user_strategy: str | None = None,
) -> dict[str, Any]:
    """Build an EQ-band plan from the best section pair in two local songs."""
    library_check = _library_level_check(song_a, song_b)
    a_analysis = dict(song_a.get("analysis") or {})
    b_analysis = dict(song_b.get("analysis") or {})
    a_analysis.setdefault("duration", song_a.get("duration"))
    b_analysis.setdefault("duration", song_b.get("duration"))
    features_a = _extract_mp3_features(song_a, a_analysis)
    features_b = _extract_mp3_features(song_b, b_analysis)
    strategy_num, strategy_name, selection_reason = StrategySelector.select(
        features_a,
        features_b,
        user_strategy=user_strategy,
    )
    strategy_params = MixingStrategyParams.get_strategy_params(strategy_num)
    fade_sec_for_scoring = max(V32_MIN_FADE_SEC, min(32.0, float(strategy_params["fade_sec"])))
    duration_beats_for_rk = int(round(fade_sec_for_scoring))

    a_outros = _transition_candidates(
        song_a,
        a_analysis,
        role="outro",
        strategy_num=strategy_num,
        default_candidates=enumerate_outro_sections(a_analysis, max_candidates=8),
        max_candidates=8,
    )
    b_intros = _transition_candidates(
        song_b,
        b_analysis,
        role="intro",
        strategy_num=strategy_num,
        default_candidates=enumerate_intro_sections(b_analysis, max_candidates=5),
        max_candidates=5,
    )
    if not a_outros or not b_intros:
        return _fallback_plan(
            song_a,
            song_b,
            library_check,
            reason="no_section_data",
            strategy_num=strategy_num,
            strategy_name=strategy_name,
            selection_reason=selection_reason,
            features_a=features_a,
            features_b=features_b,
        )

    pairs: list[dict[str, Any]] = []
    for a_section in a_outros:
        for b_section in b_intros:
            score = score_section_pair(
                a_section,
                b_section,
                song_a_bpm=_float(song_a.get("bpm"), 120.0),
                song_b_bpm=_float(song_b.get("bpm"), 120.0),
                song_a_key=str(song_a.get("camelot_key") or "8A"),
                song_b_key=str(song_b.get("camelot_key") or "8A"),
            )
            total = _float(score.get("total"), 0.0)
            from_raw = _float(a_section.get("start"), 0.0) + _float(a_section.get("cue_offset"), 0.0)
            to_raw = _float(b_section.get("start"), 0.0) + _float(b_section.get("cue_offset"), 0.0)
            from_at = _snap_to_nearest(from_raw, _downbeats(a_analysis))
            to_at = _snap_to_nearest(to_raw, _downbeats(b_analysis))
            window = _score_actual_mix_window(
                a_analysis,
                b_analysis,
                from_at_sec=from_at,
                to_at_sec=to_at,
                fade_sec=fade_sec_for_scoring,
            )
            total += _float(window.get("score_delta"), 0.0)
            breakdown = dict(score["breakdown"])
            breakdown.update(window["breakdown"])
            issues = [*score["issues"], *window["issues"]]
            if cursor_sec is not None:
                distance = abs(_float(a_section.get("start"), 0.0) - float(cursor_sec))
                penalty = max(0.0, min(5.0, (distance - 5.0) * 0.5))
                total -= penalty
                breakdown["cursor_penalty"] = -round(penalty, 1)
            pairs.append(
                {
                    "a_section": a_section,
                    "b_section": b_section,
                    "score": round(total, 1),
                    "breakdown": breakdown,
                    "strategy": strategy_name,
                    "issues": issues,
                }
            )

    clean_pairs = [
        pair
        for pair in pairs
        if not pair["breakdown"].get("hard_vocal_conflict")
        and not pair["breakdown"].get("actual_hard_vocal_conflict")
        and _float(pair["breakdown"].get("actual_both_vocal"), 0.0) < 0.25
    ]
    if clean_pairs:
        pairs = clean_pairs
    pairs.sort(key=lambda item: item["score"], reverse=True)
    best = pairs[0]
    a_section = best["a_section"]
    b_section = best["b_section"]

    from_raw = _float(a_section.get("start"), 0.0) + _float(a_section.get("cue_offset"), 0.0)
    to_raw = _float(b_section.get("start"), 0.0) + _float(b_section.get("cue_offset"), 0.0)
    from_at_sec = _snap_to_nearest(from_raw, _downbeats(a_analysis))
    to_at_sec = _snap_to_nearest(to_raw, _downbeats(b_analysis))

    plan = generate_eq_band_mix_transition(
        song_a,
        song_b,
        from_at_sec=from_at_sec,
        to_at_sec=to_at_sec,
        strategy_num=strategy_num,
        strategy_name=strategy_name,
        selection_reason=selection_reason,
        features1=features_a,
        features2=features_b,
        transition_mode="section_match",
        eq_mix_user_mode=user_strategy or "auto",
        rule_key_prefix="section_match",
        transition_seed=(
            f"section-match|{song_a.get('id') or song_a.get('song_id')}|"
            f"{song_b.get('id') or song_b.get('song_id')}|{from_at_sec:.2f}|"
            f"{to_at_sec:.2f}|{strategy_num}"
        ),
    )
    plan["duration_beats"] = duration_beats_for_rk
    plan["duration_sec"] = round(fade_sec_for_scoring, 3)
    plan["fade_sec"] = round(fade_sec_for_scoring, 3)
    plan["safety"]["fallback_mode"] = "eq_band_mix"
    plan["reason"] = [
        "Section-match selected the best local phrase exit and entry before applying AutoMixer EQ-band curves.",
        "This uses local MP3/PCM low-mid-high automation and does not require Spotify API or stems.",
        f"AutoMixer strategy {strategy_num}={strategy_name}: {selection_reason}.",
    ]
    plan["section_match"] = {
            "score": round(_float(best["score"], 0.0), 1),
            "quality": quality_tier(_float(best["score"], 0.0)),
            "strategy_reason": _describe_strategy(strategy_name, best["breakdown"]),
            "a_section": _section_debug(a_section, "out"),
            "b_section": _section_debug(b_section, "in"),
            "compatibility_breakdown": best["breakdown"],
            "issues": best["issues"],
            "library_check": library_check,
            "vocal_policy": {
                "hard_conflict_filtered": bool(clean_pairs),
                "threshold": 0.60,
                "note": "Single-sided vocals are allowed. Pairs are filtered only when outgoing and incoming vocals overlap in the actual mix window and a safer pair exists.",
            },
            "top_3_alternatives": [
                {
                    "score": round(_float(pair["score"], 0.0), 1),
                    "strategy": pair["strategy"],
                    "a_section_label": pair["a_section"].get("label"),
                    "a_section_start": round(_float(pair["a_section"].get("start"), 0.0), 2),
                    "b_section_label": pair["b_section"].get("label"),
                    "b_section_start": round(_float(pair["b_section"].get("start"), 0.0), 2),
                    "issues": pair["issues"][:3],
                }
                for pair in pairs[:3]
            ],
            "user_strategy_override": user_strategy,
            "auto_strategy_selection": plan["auto_strategy_selection"],
            "is_fallback": False,
            "cut_point_policy": _cut_point_policy_debug(a_section, b_section),
    }
    logger.info(
        "[AutoMixer] %s -> %s strategy=%s(%s) fade=%.1fs reason=%s bpm=%.1f->%.1f energy=%.2f->%.2f",
        song_a.get("id") or song_a.get("song_id"),
        song_b.get("id") or song_b.get("song_id"),
        strategy_num,
        strategy_name,
        fade_sec_for_scoring,
        selection_reason,
        features_a["bpm"],
        features_b["bpm"],
        features_a["energy"],
        features_b["energy"],
    )
    return plan


def _library_level_check(song_a: dict[str, Any], song_b: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    quality = "excellent"
    bpm_a = _float(song_a.get("bpm"), 0.0)
    bpm_b = _float(song_b.get("bpm"), 0.0)
    bpm_ratio = max(bpm_a, bpm_b) / min(bpm_a, bpm_b) if bpm_a > 0 and bpm_b > 0 else 1.0
    if bpm_ratio > 1.15:
        quality = "rough"
        issues.append(f"BPM differs by {(bpm_ratio - 1.0) * 100.0:.0f}%")
    elif bpm_ratio > 1.05:
        quality = "ok"
    try:
        key_distance = camelot_distance(str(song_a.get("camelot_key") or "8A"), str(song_b.get("camelot_key") or "8A"))
    except ValueError:
        key_distance = 3
        issues.append("invalid Camelot key")
    if key_distance >= 5:
        quality = "rough"
        issues.append(f"key distance {key_distance}")
    elif key_distance >= 3 and quality == "excellent":
        quality = "ok"
    return {
        "can_mix": True,
        "quality": quality,
        "bpm_ratio": round(bpm_ratio, 3),
        "key_distance": key_distance,
        "issues": issues,
    }


def _fallback_plan(
    song_a: dict[str, Any],
    song_b: dict[str, Any],
    library_check: dict[str, Any],
    *,
    reason: str,
    strategy_num: int,
    strategy_name: str,
    selection_reason: str,
    features_a: dict[str, float],
    features_b: dict[str, float],
) -> dict[str, Any]:
    duration = _float(song_a.get("duration"), 180.0)
    fade_sec = max(V32_MIN_FADE_SEC, float(MixingStrategyParams.get_strategy_params(strategy_num)["fade_sec"]))
    a_analysis = dict(song_a.get("analysis") or {})
    b_analysis = dict(song_b.get("analysis") or {})
    a_candidates = _transition_candidates(
        song_a,
        a_analysis,
        role="outro",
        strategy_num=strategy_num,
        default_candidates=[],
        max_candidates=1,
    )
    b_candidates = _transition_candidates(
        song_b,
        b_analysis,
        role="intro",
        strategy_num=strategy_num,
        default_candidates=[],
        max_candidates=1,
    )
    from_at = (
        _float(a_candidates[0].get("start"), 0.0) + _float(a_candidates[0].get("cue_offset"), 0.0)
        if a_candidates
        else max(0.0, duration - fade_sec - 4.0)
    )
    to_at = (
        _float(b_candidates[0].get("start"), 0.0) + _float(b_candidates[0].get("cue_offset"), 0.0)
        if b_candidates
        else 0.0
    )
    plan = generate_eq_band_mix_transition(
        song_a,
        song_b,
        from_at_sec=from_at,
        to_at_sec=to_at,
        strategy_num=strategy_num,
        strategy_name=strategy_name,
        selection_reason=selection_reason,
        features1=features_a,
        features2=features_b,
        transition_mode="section_match",
        eq_mix_user_mode="auto",
        rule_key_prefix="section_match:fallback",
        transition_seed=f"section-fallback|{song_a.get('id')}|{song_b.get('id')}|{strategy_num}",
    )
    plan["safety"]["fallback_mode"] = "eq_band_mix"
    plan["section_match"] = {
            "score": 0,
            "quality": "fallback",
            "strategy_reason": f"Fallback: {reason}",
            "library_check": library_check,
            "auto_strategy_selection": plan["auto_strategy_selection"],
            "is_fallback": True,
            "cut_point_policy": _cut_point_policy_debug(
                a_candidates[0] if a_candidates else {},
                b_candidates[0] if b_candidates else {},
            ),
    }
    return plan


def _strategy_override(value: str | None) -> str | None:
    if not value or value == "auto":
        return None
    allowed = {"standard_blend", "energy_lift", "energy_drop", "tempo_compat", "cross_style"}
    aliases = {
        "1": "standard_blend",
        "smooth": "standard_blend",
        "smooth_blend": "standard_blend",
        "2": "energy_lift",
        "filter": "energy_lift",
        "filter_sweep": "energy_lift",
        "soft_bass_swap": "energy_lift",
        "3": "energy_drop",
        "vocal": "energy_drop",
        "vocal_safe": "energy_drop",
        "4": "tempo_compat",
        "rhythm": "tempo_compat",
        "hard_bass_swap": "tempo_compat",
        "5": "cross_style",
        "overlap": "cross_style",
    }
    raw = value.strip().lower()
    mapped = aliases.get(raw, raw)
    return mapped if mapped in allowed else None


def _section_debug(section: dict[str, Any], direction: str) -> dict[str, Any]:
    debug = {
        "direction": direction,
        "label": section.get("label"),
        "start": round(_float(section.get("start"), 0.0), 2),
        "end": round(_float(section.get("end"), 0.0), 2),
        "duration": round(_float(section.get("duration"), 0.0), 2),
        "priority": section.get("priority"),
        "priority_reason": section.get("priority_reason", "default"),
        "vocal_density_start": round(_float(section.get("vocal_density_start"), 0.0), 2),
        "vocal_density_end": round(_float(section.get("vocal_density_end"), 0.0), 2),
        "vocal_density_avg": round(_float(section.get("vocal_density_avg"), 0.0), 2),
        "low_band_energy": round(_float(section.get("low_band_energy"), 0.0), 2),
        "loudness_start_db": round(_float(section.get("loudness_start"), -10.0), 1),
        "loudness_end_db": round(_float(section.get("loudness_end"), -10.0), 1),
    }
    if section.get("exit_progress") is not None:
        debug["exit_progress"] = round(_float(section.get("exit_progress"), 0.0), 3)
    if section.get("cut_point_source"):
        debug["cut_point_source"] = section.get("cut_point_source")
        debug["cut_point_detail"] = section.get("cut_point_detail") or {}
    return debug


def _transition_candidates(
    song: dict[str, Any],
    analysis: dict[str, Any],
    *,
    role: str,
    strategy_num: int,
    default_candidates: list[dict[str, Any]],
    max_candidates: int,
) -> list[dict[str, Any]]:
    """Prefer stem-aware points, fallback to MP3 beat/bar, then old phrase data."""
    if _has_stem_point_data(analysis):
        try:
            audio_path = _song_audio_path(song)
            candidates = build_transition_point_candidates(
                analysis,
                role=role,
                strategy_num=strategy_num,
                audio_path=audio_path,
                max_candidates=max_candidates,
            )
            if candidates:
                return candidates
        except Exception as exc:
            logger.warning(
                "[AutoMixer] stem-aware transition point selection failed for %s role=%s: %s",
                song.get("id") or song.get("song_id"),
                role,
                exc,
            )
        return default_candidates

    try:
        audio_path = _song_audio_path(song)
        candidates = build_transition_point_candidates(
            analysis,
            role=role,
            strategy_num=strategy_num,
            audio_path=audio_path,
            max_candidates=max_candidates,
        )
        if candidates:
            return candidates
    except Exception as exc:
        logger.warning(
            "[AutoMixer] transition point fallback failed for %s role=%s: %s",
            song.get("id") or song.get("song_id"),
            role,
            exc,
        )
    return default_candidates


def _has_stem_point_data(analysis: dict[str, Any]) -> bool:
    if analysis.get("stem_activity_windows"):
        return True
    raw = analysis.get("transition_windows")
    if isinstance(raw, list):
        return any(
            isinstance(item, dict) and (item.get("stem_snapshot") or item.get("stem_tags"))
            for item in raw
        )
    return False


def _song_audio_path(song: dict[str, Any]) -> str | None:
    for key in ("source_path", "audio_path", "file_path", "path"):
        value = song.get(key)
        if value:
            return str(value)
    return None


def _cut_point_policy_debug(a_section: dict[str, Any], b_section: dict[str, Any]) -> dict[str, Any]:
    return {
        "frequency_mix_requires": ["original_mp3", "analysis_plan"],
        "stem_audio_required": False,
        "exit_source": a_section.get("cut_point_source") or a_section.get("priority_reason") or "phrase_map",
        "entry_source": b_section.get("cut_point_source") or b_section.get("priority_reason") or "phrase_map",
        "stem_priority": "use stem-enhanced transition_windows when present",
        "fallback": "beat+4/4-bar analysis from MP3 when stem transition points are missing",
    }


def _score_actual_mix_window(
    a_analysis: dict[str, Any],
    b_analysis: dict[str, Any],
    *,
    from_at_sec: float,
    to_at_sec: float,
    fade_sec: float,
) -> dict[str, Any]:
    """Score the exact windows RK will overlap, not just section edges."""
    a_duration = _float(a_analysis.get("duration"), 0.0)
    b_duration = _float(b_analysis.get("duration"), 0.0)
    a_end = min(a_duration, from_at_sec + fade_sec) if a_duration > from_at_sec else from_at_sec + fade_sec
    b_end = min(b_duration, to_at_sec + fade_sec) if b_duration > to_at_sec else to_at_sec + fade_sec
    a_vocal = _actual_vocal_density(a_analysis, from_at_sec, a_end)
    b_vocal = _actual_vocal_density(b_analysis, to_at_sec, b_end)
    both_vocal = min(a_vocal, b_vocal)
    max_vocal = max(a_vocal, b_vocal)
    score_delta = 0.0
    issues: list[str] = []
    hard_conflict = False

    if a_vocal >= 0.60 and b_vocal >= 0.60:
        hard_conflict = True
        score_delta -= 45.0
        issues.append("actual 6s mix window has hard double vocal overlap")
    elif both_vocal >= 0.25:
        hard_conflict = True
        score_delta -= 30.0
        issues.append("actual 6s mix window has double vocal overlap")
    elif both_vocal >= 0.10:
        score_delta -= 8.0
        issues.append("actual 6s mix window has light double vocal overlap")
    elif max_vocal >= 0.45:
        score_delta += 4.0
    elif max_vocal >= 0.10:
        score_delta += 2.0
    else:
        score_delta += 6.0

    if a_duration > 0:
        progress = from_at_sec / a_duration
        if progress > 0.96:
            score_delta -= 18.0
            issues.append("exit point is too close to song end")
        elif progress > 0.90:
            score_delta -= 9.0
            issues.append("exit point is very late in the song")
        elif 0.38 <= progress <= 0.78:
            score_delta += 8.0

    return {
        "score_delta": round(score_delta, 1),
        "issues": issues,
        "breakdown": {
            "actual_window": round(score_delta, 1),
            "actual_a_vocal": round(a_vocal, 3),
            "actual_b_vocal": round(b_vocal, 3),
            "actual_both_vocal": round(both_vocal, 3),
            "actual_max_vocal": round(max_vocal, 3),
            "actual_one_sided_vocal_allowed": bool(max_vocal >= 0.25 and both_vocal < 0.10),
            "actual_hard_vocal_conflict": hard_conflict,
            "actual_from_window": [round(from_at_sec, 3), round(a_end, 3)],
            "actual_to_window": [round(to_at_sec, 3), round(b_end, 3)],
        },
    }


def _actual_vocal_density(analysis: dict[str, Any], start: float, end: float) -> float:
    events = analysis.get("vocal_events") or []
    if events:
        return vocal_density_in_range(events, start, end)
    stem_windows = analysis.get("stem_activity_windows") or []
    if isinstance(stem_windows, list) and stem_windows and end > start:
        weighted = 0.0
        total = 0.0
        for window in stem_windows:
            if not isinstance(window, dict):
                continue
            w_start = _float(window.get("start", window.get("start_sec")), 0.0)
            w_end = _float(window.get("end", window.get("end_sec")), w_start)
            overlap = max(0.0, min(end, w_end) - max(start, w_start))
            if overlap <= 0:
                continue
            weighted += overlap * _float(window.get("vocals"), 0.0)
            total += overlap
        if total > 0:
            return max(0.0, min(1.0, weighted / total))
    return 0.0


def _describe_strategy(strategy: str, breakdown: dict[str, Any]) -> str:
    if strategy == "standard_blend":
        return "Strategy 1 from auto_dj_mix.py: similar BPM/energy, standard three-band frequency blend."
    if strategy == "energy_lift":
        return "Strategy 2 from auto_dj_mix.py: incoming energy is higher, use the energy-lift frequency curve."
    if strategy == "energy_drop":
        return "Strategy 3 from auto_dj_mix.py: incoming energy is lower, use the energy-drop frequency curve."
    if strategy == "tempo_compat":
        return "Strategy 4 from auto_dj_mix.py: BPM difference is large, use the standard-compatible curve."
    if strategy == "cross_style":
        return "Strategy 5 from auto_dj_mix.py: frequency distribution differs strongly, use cross-style blend."
    return f"Strategy {strategy}"


def _snap_to_nearest(time_sec: float, points: list[float], *, tolerance_sec: float = 1.0) -> float:
    if not points:
        return time_sec
    nearest = min(points, key=lambda point: abs(point - time_sec))
    return nearest if abs(nearest - time_sec) <= tolerance_sec else time_sec


def _downbeats(analysis: dict[str, Any]) -> list[float]:
    beatgrid = analysis.get("beatgrid") if isinstance(analysis.get("beatgrid"), dict) else {}
    raw = beatgrid.get("downbeats") or analysis.get("downbeats") or []
    if not isinstance(raw, list):
        return []
    out: list[float] = []
    for item in raw:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            continue
    return out


def _strategy_feature_payload(song: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "bpm": song.get("bpm"),
        "energy": song.get("energy"),
        "source_path": song.get("source_path") or song.get("audio_path") or song.get("file_path"),
        "phrase_map": analysis.get("phrase_map") or [],
        "music_features": song.get("music_features") or {},
        "loudness_profile": song.get("loudness_profile") or {},
        "genre_profile": song.get("genre_profile") or {},
        "stem_activity": song.get("stem_activity") or {},
        "bass_risk_windows": analysis.get("bass_risk_windows") or [],
        "vocal_events": analysis.get("vocal_events") or [],
    }


def _extract_mp3_features(song: dict[str, Any], analysis: dict[str, Any]) -> dict[str, float]:
    payload = _strategy_feature_payload(song, analysis)
    song_id = str(song.get("id") or song.get("song_id") or "")
    try:
        song_path = get_song_file_path(song_id, payload)
        return FeatureAnalyzer.extract_features(song_path, payload)
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        logger.warning(
            "[AutoMixer] real MP3 feature analysis unavailable for %s: %s",
            song_id,
            exc,
        )
        return FeatureAnalyzer.extract_features(payload)


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
