"""Section-level feature extraction for local Spotify-style mixing."""

from __future__ import annotations

import math
from typing import Any


ROLE_INTRO = "intro"
ROLE_OUTRO = "outro"
ROLE_MIDDLE = "middle"

DEFAULT_VOCAL_DENSITY = 0.55
DEFAULT_LOW_ENERGY = 0.5


def _structure_label(phrase: dict[str, Any]) -> str:
    label = str(
        phrase.get("structure_label_candidate")
        or phrase.get("label")
        or phrase.get("type")
        or "unknown"
    ).strip().lower()
    return "instrumental" if label == "inst" else label


def _mix_roles(phrase: dict[str, Any]) -> list[str]:
    raw = phrase.get("mix_roles") or []
    if not isinstance(raw, (list, tuple, set)):
        return []
    return [str(role).strip().lower() for role in raw if str(role).strip()]


def extract_section_features(
    phrase: dict[str, Any],
    song_analysis: dict[str, Any],
    *,
    role: str = ROLE_MIDDLE,
) -> dict[str, Any]:
    """Return the local mix features needed to score one phrase/section."""
    start = _float(phrase.get("start", phrase.get("start_sec", phrase.get("time"))), 0.0)
    end = _float(phrase.get("end", phrase.get("end_sec")), start)
    duration = max(0.0, end - start)
    label = _structure_label(phrase)
    mix_roles = _mix_roles(phrase)
    raw_role_scores = phrase.get("mix_role_scores")
    mix_role_scores = dict(raw_role_scores) if isinstance(raw_role_scores, dict) else {}
    energy = _float(phrase.get("energy", phrase.get("intensity")), 0.5)

    energy_curve = song_analysis.get("energy_curve") or []
    vocal_events = song_analysis.get("vocal_events") or []
    bass_windows = song_analysis.get("bass_risk_windows") or []
    downbeats = _downbeats(song_analysis)

    return {
        "start": start,
        "end": end,
        "duration": duration,
        "label": label,
        "structure_label_candidate": label,
        "mix_roles": mix_roles,
        "mix_role_scores": mix_role_scores,
        "role": role,
        "energy": energy,
        "intensity": _float(phrase.get("intensity"), energy),
        "priority": _base_priority(label, role, mix_roles=mix_roles),
        "cue_offset": _cue_offset(label, role, duration, mix_roles=mix_roles),
        "loudness_start": _energy_to_loudness(_sample_energy_at(energy_curve, start)),
        "loudness_end": _energy_to_loudness(_sample_energy_at(energy_curve, max(start, end - 0.5))),
        "vocal_density_start": _vocal_density_in_range(vocal_events, start, min(end, start + 4.0)),
        "vocal_density_end": _vocal_density_in_range(vocal_events, max(start, end - 4.0), end),
        "vocal_density_avg": _vocal_density_in_range(vocal_events, start, end),
        "low_band_energy": _low_band_energy_in_range(bass_windows, start, end),
        "starts_at_downbeat": _is_near_downbeat(start, downbeats),
        "ends_at_downbeat": _is_near_downbeat(end, downbeats),
        "tempo": _sample_bpm_at(song_analysis.get("bpm_curve") or [], (start + end) / 2.0),
    }


def enumerate_outro_sections(song_analysis: dict[str, Any], *, max_candidates: int = 8) -> list[dict[str, Any]]:
    """Pick candidate exit sections from the previous song."""
    phrases = _phrases(song_analysis)
    if not phrases:
        return []

    duration = _float(song_analysis.get("duration"), 0.0)
    min_exit_at = _minimum_musical_exit_time(duration)
    candidates: list[dict[str, Any]] = []
    for idx, phrase in enumerate(phrases):
        feature = extract_section_features(phrase, song_analysis, role=ROLE_OUTRO)
        label = feature["label"]
        mix_roles = set(feature["mix_roles"])
        cue_time = feature["start"] + feature["cue_offset"]
        if duration > 0 and cue_time < min_exit_at:
            continue
        if label == "outro":
            feature.update(priority=92, priority_reason="outro_label")
        elif label in {"chorus", "drop"}:
            feature.update(priority=88, priority_reason="mid_late_peak_exit")
        elif "transition" in mix_roles:
            feature.update(priority=86, priority_reason="transition_role_exit")
        elif label in {"break", "bridge", "instrumental"}:
            feature.update(priority=84, priority_reason="mid_late_break_exit")
        elif label == "verse" and idx >= 2:
            feature.update(priority=62, priority_reason="mid_late_verse_exit")
        elif duration > 0 and feature["start"] >= duration - 30.0:
            feature.update(priority=70, priority_reason="last_30s")
        elif idx >= len(phrases) - 3:
            feature.update(priority=50, priority_reason="last_3_phrases")
        else:
            continue
        feature = _adjust_priority_for_exit_timing(feature, duration)
        feature = _adjust_priority_for_vocal_safety(feature, edge="end")
        candidates.append(feature)

    return sorted(candidates, key=lambda item: item["priority"], reverse=True)[:max_candidates]


def enumerate_intro_sections(song_analysis: dict[str, Any], *, max_candidates: int = 3) -> list[dict[str, Any]]:
    """Pick candidate entry sections from the next song."""
    phrases = _phrases(song_analysis)
    if not phrases:
        return []

    candidates: list[dict[str, Any]] = []
    for idx, phrase in enumerate(phrases[:5]):
        feature = extract_section_features(phrase, song_analysis, role=ROLE_INTRO)
        label = feature["label"]
        mix_roles = set(feature["mix_roles"])
        if label == "chorus":
            feature.update(priority=100, priority_reason="first_chorus")
        elif label == "drop":
            feature.update(priority=95, priority_reason="first_drop")
        elif "buildup" in mix_roles:
            feature.update(priority=85, priority_reason="buildup_role_entry")
        elif label == "verse" and idx <= 2:
            feature.update(priority=80, priority_reason="early_verse")
        elif label == "intro" and idx == 0:
            feature.update(
                priority=60,
                cue_offset=feature["duration"] * 0.7,
                priority_reason="intro_late",
            )
        elif idx == 0:
            feature.update(priority=40, priority_reason="first_phrase_default")
        else:
            continue
        feature = _adjust_priority_for_vocal_safety(feature, edge="start")
        candidates.append(feature)

    return sorted(candidates, key=lambda item: item["priority"], reverse=True)[:max_candidates]


def _phrases(song_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    raw = song_analysis.get("phrase_map") or song_analysis.get("phrases") or []
    if not isinstance(raw, list):
        return []
    phrases = [item for item in raw if isinstance(item, dict)]
    return sorted(phrases, key=lambda item: _float(item.get("start", item.get("start_sec")), 0.0))


def _downbeats(song_analysis: dict[str, Any]) -> list[float]:
    beatgrid = song_analysis.get("beatgrid") if isinstance(song_analysis.get("beatgrid"), dict) else {}
    raw = beatgrid.get("downbeats") or song_analysis.get("downbeats") or []
    if not isinstance(raw, list):
        return []
    values: list[float] = []
    for item in raw:
        try:
            values.append(float(item))
        except (TypeError, ValueError):
            continue
    return values


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sample_energy_at(energy_curve: list[Any], time_sec: float) -> float:
    if not isinstance(energy_curve, list) or not energy_curve:
        return DEFAULT_LOW_ENERGY
    points: list[tuple[float, float]] = []
    for item in energy_curve:
        if isinstance(item, dict):
            points.append((_float(item.get("time", item.get("sec")), 0.0), _float(item.get("energy", item.get("value")), DEFAULT_LOW_ENERGY)))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            points.append((_float(item[0], 0.0), _float(item[1], DEFAULT_LOW_ENERGY)))
    if not points:
        return DEFAULT_LOW_ENERGY
    return min(points, key=lambda point: abs(point[0] - time_sec))[1]


def _sample_bpm_at(bpm_curve: list[Any], time_sec: float) -> float | None:
    if not isinstance(bpm_curve, list) or not bpm_curve:
        return None
    points: list[tuple[float, float]] = []
    for item in bpm_curve:
        if isinstance(item, dict):
            bpm = item.get("bpm", item.get("tempo"))
            if bpm is not None:
                points.append((_float(item.get("time", item.get("sec")), 0.0), _float(bpm, 0.0)))
    if not points:
        return None
    bpm = min(points, key=lambda point: abs(point[0] - time_sec))[1]
    return bpm if bpm > 0 else None


def _energy_to_loudness(energy: float) -> float:
    if energy <= 0:
        return -60.0
    return max(-60.0, min(0.0, 20.0 * math.log10(max(0.001, energy)) - 3.0))


def _vocal_density_in_range(events: list[Any], start: float, end: float) -> float:
    if not isinstance(events, list) or not events or end <= start:
        return DEFAULT_VOCAL_DENSITY
    ranges = _vocal_event_ranges(events, query_end=end)
    total = 0.0
    for ev_start, ev_end, confidence in ranges:
        overlap = max(0.0, min(end, ev_end) - max(start, ev_start))
        total += overlap * confidence
    return min(1.0, total / (end - start))


def vocal_density_in_range(events: list[Any], start: float, end: float) -> float:
    """Public wrapper used by the section matcher for the actual mix window."""
    return _vocal_density_in_range(events, start, end)


def _vocal_event_ranges(events: list[Any], *, query_end: float) -> list[tuple[float, float, float]]:
    """Normalize old enter/exit vocal markers and new start/end ranges.

    Old analysis stored events as `{time, type: enter|exit}` markers. New GPU
    backfill stores `{start, end}` ranges. The mixer needs ranges, otherwise old
    library songs are incorrectly treated as vocal-clean.
    """
    ranges: list[tuple[float, float, float]] = []
    markers: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if "start" in event or "end" in event:
            ev_start = _float(event.get("start", event.get("time")), 0.0)
            ev_end = _float(event.get("end"), ev_start + _float(event.get("duration"), 0.0))
            if ev_end > ev_start:
                ranges.append((ev_start, ev_end, _float(event.get("confidence"), 1.0)))
            continue
        if "time" in event and "type" in event:
            markers.append(event)

    if not markers:
        return ranges

    active_start: float | None = None
    active_confidence = 1.0
    for marker in sorted(markers, key=lambda item: _float(item.get("time"), 0.0)):
        t = _float(marker.get("time"), 0.0)
        kind = str(marker.get("type") or "").lower()
        confidence = _float(marker.get("confidence"), 1.0)
        if kind == "enter":
            if active_start is None:
                active_start = t
                active_confidence = confidence
            else:
                active_confidence = max(active_confidence, confidence)
        elif kind == "exit" and active_start is not None:
            if t > active_start:
                ranges.append((active_start, t, active_confidence))
            active_start = None
            active_confidence = 1.0

    if active_start is not None:
        ranges.append((active_start, max(query_end, active_start), active_confidence))
    return ranges


def _adjust_priority_for_vocal_safety(section: dict[str, Any], *, edge: str) -> dict[str, Any]:
    """Keep vocal metadata without rejecting a single vocal side.

    Pair scoring is the only place that can know whether both decks carry vocals
    at the same time.  A vocal on only the outgoing or incoming song is allowed,
    so candidate enumeration must not hide useful sections just because one
    edge contains vocals.
    """
    vocal_key = "vocal_density_end" if edge == "end" else "vocal_density_start"
    vocal = _float(section.get(vocal_key), DEFAULT_VOCAL_DENSITY)
    adjusted = dict(section)
    adjusted["single_edge_vocal_density"] = round(vocal, 3)
    return adjusted


def _minimum_musical_exit_time(duration: float) -> float:
    if duration <= 0:
        return 0.0
    return min(max(45.0, duration * 0.25), max(0.0, duration - 30.0))


def _adjust_priority_for_exit_timing(section: dict[str, Any], duration: float) -> dict[str, Any]:
    """Prefer musical mid/late exits without forcing every mix to the song tail."""
    if duration <= 0:
        return section
    adjusted = dict(section)
    cue_time = _float(adjusted.get("start"), 0.0) + _float(adjusted.get("cue_offset"), 0.0)
    progress = cue_time / duration
    delta = 0
    reason = "timing_neutral"
    if 0.38 <= progress <= 0.78:
        delta = 14
        reason = "ideal_mid_late_exit"
    elif 0.78 < progress <= 0.88:
        delta = 4
        reason = "late_but_usable_exit"
    elif progress > 0.94:
        delta = -24
        reason = "too_close_to_song_end"
    elif progress > 0.88:
        delta = -12
        reason = "very_late_exit"
    adjusted["priority"] = max(0, _float(adjusted.get("priority"), 40.0) + delta)
    adjusted["exit_progress"] = round(progress, 3)
    if reason != "timing_neutral":
        adjusted["priority_reason"] = f"{adjusted.get('priority_reason', 'default')}_{reason}"
    return adjusted


def _low_band_energy_in_range(windows: list[Any], start: float, end: float) -> float:
    if not isinstance(windows, list) or not windows or end <= start:
        return DEFAULT_LOW_ENERGY
    weighted = 0.0
    overlap_total = 0.0
    for window in windows:
        if not isinstance(window, dict):
            continue
        w_start = _float(window.get("start", window.get("start_sec")), 0.0)
        w_end = _float(window.get("end", window.get("end_sec")), w_start)
        overlap = max(0.0, min(end, w_end) - max(start, w_start))
        if overlap <= 0:
            continue
        weighted += overlap * _float(window.get("low_energy", window.get("energy")), DEFAULT_LOW_ENERGY)
        overlap_total += overlap
    if overlap_total <= 0:
        return DEFAULT_LOW_ENERGY
    covered = overlap_total / (end - start)
    return (weighted / overlap_total) * covered + DEFAULT_LOW_ENERGY * (1.0 - covered)


def _is_near_downbeat(time_sec: float, downbeats: list[float], *, tolerance_sec: float = 0.3) -> bool:
    return any(abs(db - time_sec) <= tolerance_sec for db in downbeats)


def _base_priority(
    label: str,
    role: str,
    *,
    mix_roles: list[str] | tuple[str, ...] = (),
) -> int:
    roles = set(mix_roles)
    if role == ROLE_OUTRO:
        if "transition" in roles:
            return 86
        return {"outro": 100, "chorus": 80, "verse": 50}.get(label, 30)
    if role == ROLE_INTRO:
        if "buildup" in roles:
            return 85
        return {"chorus": 100, "drop": 95, "verse": 70, "intro": 50}.get(label, 30)
    return 40


def _cue_offset(
    label: str,
    role: str,
    duration: float,
    *,
    mix_roles: list[str] | tuple[str, ...] = (),
) -> float:
    if role == ROLE_OUTRO:
        if "transition" in mix_roles:
            return duration * 0.5
        return duration * (0.6 if label in {"outro", "chorus"} else 0.5)
    if role == ROLE_INTRO and label == "intro":
        return duration * 0.7
    return 0.0
