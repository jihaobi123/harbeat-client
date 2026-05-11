from __future__ import annotations

from typing import Any, Optional

from app.modules.playlists.schemas import DjTransitionPlanItem

FULL_MIX_MIN_SCORE = 0.65
SHORT_FADE_MIN_SCORE = 0.40
MIN_BEAT_CONFIDENCE = 0.55
ONLINE_SAFE_TEMPO_SHIFT = 0.06
ONLINE_MAX_TEMPO_SHIFT = 0.10
MIN_FULL_CROSSFADE_SEC = 4.0
MAX_FULL_CROSSFADE_SEC = 16.0
DEFAULT_SHORT_FADE_SEC = 2.5
PRELOAD_BEFORE_TRANSITION_SEC = 20.0
MIN_PREPARE_SEC = 6.0

OnlineMixMode = str


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _song_attr(song: object, name: str, default: object = None) -> object:
    if song is None:
        return default
    if isinstance(song, dict):
        return song.get(name, default)
    return getattr(song, name, default)


def _beat_confidence(song: object) -> Optional[float]:
    value = _song_attr(song, "beat_confidence")
    if value is not None:
        return _clamp(_safe_float(value, 0.0), 0.0, 1.0)

    beat_analysis = _song_attr(song, "beat_analysis")
    value = _song_attr(beat_analysis, "beat_confidence")
    if value is not None:
        return _clamp(_safe_float(value, 0.0), 0.0, 1.0)
    return None


def _has_sufficient_beats(song: object) -> bool:
    beat_analysis = _song_attr(song, "beat_analysis")
    beat_usable = _song_attr(beat_analysis, "beat_usable")
    beat_count = _song_attr(beat_analysis, "beat_count")
    if beat_usable is not None or beat_count is not None:
        return bool(beat_usable) and _safe_float(beat_count, 0.0) >= 8

    beat_points = _song_attr(song, "beat_points")
    if isinstance(beat_points, list):
        return len(beat_points) >= 8

    beatgrid = _song_attr(song, "beatgrid")
    beats = _song_attr(beatgrid, "beats")
    return isinstance(beats, list) and len(beats) >= 8


def _duration(song: object) -> float:
    return _safe_float(
        _song_attr(song, "duration", _song_attr(song, "duration_seconds", 0.0)),
        0.0,
    )


def _bpm(song: object) -> Optional[float]:
    value = _song_attr(song, "bpm")
    if value is None:
        beatgrid = _song_attr(song, "beatgrid")
        value = _song_attr(beatgrid, "bpm")
    bpm = _safe_float(value, 0.0)
    return bpm if bpm > 0 else None


def _normalized_tempo_ratio(from_song: object, to_song: object, transition_plan: DjTransitionPlanItem) -> float:
    from_bpm = _bpm(from_song)
    to_bpm = _bpm(to_song)
    if from_bpm and to_bpm:
        ratio = to_bpm / from_bpm
        return float(min([ratio, ratio / 2.0, ratio * 2.0], key=lambda x: abs(1.0 - x)))
    return _safe_float(transition_plan.tempo_ratio, 1.0) or 1.0


def _valid_timing(transition_plan: DjTransitionPlanItem) -> bool:
    entry = transition_plan.entry_time_sec
    exit_ = transition_plan.exit_time_sec
    return entry is not None and exit_ is not None and entry >= 0 and exit_ >= 0


def score_online_mix_safety(
    from_song: object,
    to_song: object,
    transition_plan: DjTransitionPlanItem,
) -> dict[str, Any]:
    score = _safe_float(transition_plan.score, 0.0)
    tempo_ratio = _normalized_tempo_ratio(from_song, to_song, transition_plan)
    tempo_shift = abs(tempo_ratio - 1.0)
    from_conf = _beat_confidence(from_song)
    to_conf = _beat_confidence(to_song)
    known_conf = [v for v in (from_conf, to_conf) if v is not None]
    min_beat_conf = min(known_conf) if known_conf else 0.0
    has_beats = _has_sufficient_beats(from_song) and _has_sufficient_beats(to_song)
    crossfade = _safe_float(transition_plan.crossfade_sec, 0.0)
    timing_ok = _valid_timing(transition_plan)
    from_duration = _duration(from_song)
    to_duration = _duration(to_song)
    duration_ok = from_duration > crossfade + 2.0 and to_duration > 1.0

    reasons: list[str] = []
    blockers: list[str] = []

    if score >= FULL_MIX_MIN_SCORE:
        reasons.append("transition score high")
    elif score >= SHORT_FADE_MIN_SCORE:
        reasons.append("transition score usable for fallback")
    else:
        blockers.append("transition score too low for full mix")

    if tempo_shift <= ONLINE_SAFE_TEMPO_SHIFT:
        reasons.append("tempo ratio within online safe range")
    elif tempo_shift <= ONLINE_MAX_TEMPO_SHIFT:
        reasons.append("tempo ratio requires short fade fallback")
    else:
        blockers.append("tempo ratio exceeds online mix range")

    if min_beat_conf >= MIN_BEAT_CONFIDENCE and has_beats:
        reasons.append("beat confidence sufficient")
    else:
        blockers.append("beat information insufficient for full mix")

    if MIN_FULL_CROSSFADE_SEC <= crossfade <= MAX_FULL_CROSSFADE_SEC:
        reasons.append("crossfade duration suitable")
    elif crossfade < MIN_FULL_CROSSFADE_SEC:
        blockers.append("crossfade duration too short for full mix")
    else:
        reasons.append("crossfade duration will be capped for online mix")

    if timing_ok:
        reasons.append("entry and exit timing available")
    else:
        blockers.append("entry or exit timing unavailable")

    if duration_ok:
        reasons.append("track durations sufficient")
    else:
        blockers.append("track duration invalid or too short")

    full_mix_ok = (
        score >= FULL_MIX_MIN_SCORE
        and tempo_shift <= ONLINE_SAFE_TEMPO_SHIFT
        and min_beat_conf >= MIN_BEAT_CONFIDENCE
        and has_beats
        and crossfade >= MIN_FULL_CROSSFADE_SEC
        and timing_ok
        and duration_ok
    )

    if full_mix_ok:
        recommended_mode: OnlineMixMode = "full_mix"
        fallback_mode: OnlineMixMode = "short_fade"
    elif timing_ok and duration_ok and score >= SHORT_FADE_MIN_SCORE and tempo_shift <= ONLINE_MAX_TEMPO_SHIFT:
        recommended_mode = "short_fade"
        fallback_mode = "hard_cut"
    else:
        recommended_mode = "hard_cut"
        fallback_mode = "hard_cut"

    return {
        "online_mix_safe": full_mix_ok,
        "recommended_mode": recommended_mode,
        "fallback_mode": fallback_mode,
        "min_prepare_sec": MIN_PREPARE_SEC,
        "preload_before_sec": PRELOAD_BEFORE_TRANSITION_SEC,
        "reasons": reasons + blockers,
    }


def build_mix_control_timeline(
    from_song: object,
    to_song: object,
    transition_plan: DjTransitionPlanItem,
    mode: str,
) -> dict[str, Any]:
    safety_duration = _safe_float(transition_plan.crossfade_sec, DEFAULT_SHORT_FADE_SEC)
    if mode == "full_mix":
        duration = _clamp(safety_duration, MIN_FULL_CROSSFADE_SEC, MAX_FULL_CROSSFADE_SEC)
    elif mode == "short_fade":
        duration = _clamp(safety_duration if safety_duration > 0 else DEFAULT_SHORT_FADE_SEC, 1.5, 3.0)
    else:
        duration = 0.0

    from_song_id = int(_song_attr(from_song, "song_id", transition_plan.from_song_id) or transition_plan.from_song_id)
    to_song_id = int(_song_attr(to_song, "song_id", transition_plan.to_song_id) or transition_plan.to_song_id)
    entry_position = _safe_float(transition_plan.entry_time_sec, 0.0)
    start_at = _safe_float(transition_plan.phase_anchor_sec, 0.0)
    tempo_ratio = _normalized_tempo_ratio(from_song, to_song, transition_plan)
    playback_rate = tempo_ratio if mode == "full_mix" and abs(tempo_ratio - 1.0) <= ONLINE_SAFE_TEMPO_SHIFT else 1.0

    events: list[dict[str, Any]] = [
        {
            "type": "deck_load",
            "deck": "B",
            "time_sec": -PRELOAD_BEFORE_TRANSITION_SEC,
            "song_id": to_song_id,
            "position_sec": round(entry_position, 3),
        }
    ]

    if mode == "hard_cut":
        events.extend(
            [
                {
                    "type": "deck_play",
                    "deck": "B",
                    "time_sec": 0.0,
                    "position_sec": round(entry_position, 3),
                    "playback_rate": 1.0,
                    "key_lock": False,
                },
                {"type": "deck_stop", "deck": "A", "time_sec": 0.05},
            ]
        )
    else:
        events.extend(
            [
                {
                    "type": "deck_play",
                    "deck": "B",
                    "time_sec": 0.0,
                    "position_sec": round(entry_position, 3),
                    "playback_rate": round(playback_rate, 5),
                    "key_lock": mode == "full_mix" and playback_rate != 1.0,
                },
                {
                    "type": "param_ramp",
                    "deck": "A",
                    "time_sec": 0.0,
                    "duration_sec": round(duration, 3),
                    "param": "gain",
                    "from": 1.0,
                    "to": 0.0,
                    "curve": "equal_power_out" if mode == "full_mix" else "linear",
                },
                {
                    "type": "param_ramp",
                    "deck": "B",
                    "time_sec": 0.0,
                    "duration_sec": round(duration, 3),
                    "param": "gain",
                    "from": 0.0,
                    "to": 1.0,
                    "curve": "equal_power_in" if mode == "full_mix" else "linear",
                },
            ]
        )

        technique = (transition_plan.transition_technique or "").lower()
        if mode == "full_mix" and technique in {"eq_bass_swap", "bass_swap", "echo_style_cross"}:
            events.extend(
                [
                    {
                        "type": "param_ramp",
                        "deck": "A",
                        "time_sec": round(duration * 0.35, 3),
                        "duration_sec": round(duration * 0.3, 3),
                        "param": "low_eq",
                        "from": 1.0,
                        "to": 0.35,
                        "curve": "ease_in_out",
                    },
                    {
                        "type": "param_ramp",
                        "deck": "B",
                        "time_sec": 0.0,
                        "duration_sec": round(duration * 0.55, 3),
                        "param": "low_eq",
                        "from": 0.35,
                        "to": 1.0,
                        "curve": "ease_in_out",
                    },
                    {
                        "type": "param_ramp",
                        "deck": "A",
                        "time_sec": round(duration * 0.5, 3),
                        "duration_sec": round(duration * 0.35, 3),
                        "param": "highpass_hz",
                        "from": 20.0,
                        "to": 120.0,
                        "curve": "ease_in_out",
                    },
                    {
                        "type": "param_ramp",
                        "deck": "B",
                        "time_sec": 0.0,
                        "duration_sec": round(duration * 0.4, 3),
                        "param": "highpass_hz",
                        "from": 90.0,
                        "to": 20.0,
                        "curve": "ease_in_out",
                    },
                ]
            )
        elif mode == "full_mix":
            events.extend(
                [
                    {
                        "type": "param_ramp",
                        "deck": "A",
                        "time_sec": 0.0,
                        "duration_sec": round(duration, 3),
                        "param": "low_eq",
                        "from": 1.0,
                        "to": 0.6,
                        "curve": "ease_in_out",
                    },
                    {
                        "type": "param_ramp",
                        "deck": "B",
                        "time_sec": 0.0,
                        "duration_sec": round(duration, 3),
                        "param": "low_eq",
                        "from": 0.6,
                        "to": 1.0,
                        "curve": "ease_in_out",
                    },
                ]
            )

        events.append({"type": "deck_stop", "deck": "A", "time_sec": round(duration + 0.1, 3)})

    return {
        "transition_id": f"{from_song_id}_to_{to_song_id}",
        "mode": mode,
        "start_at_from_time_sec": round(start_at, 3),
        "duration_sec": round(duration, 3),
        "events": events,
    }


def build_online_transition_payload(
    from_song: object,
    to_song: object,
    transition_plan: DjTransitionPlanItem,
) -> dict[str, Any]:
    safety = score_online_mix_safety(from_song, to_song, transition_plan)
    timeline = build_mix_control_timeline(
        from_song=from_song,
        to_song=to_song,
        transition_plan=transition_plan,
        mode=str(safety["recommended_mode"]),
    )
    return {
        "online_mix_safety": safety,
        "mix_control_timeline": timeline,
    }
