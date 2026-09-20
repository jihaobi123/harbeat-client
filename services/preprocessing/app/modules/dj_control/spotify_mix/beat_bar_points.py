"""MP3-only beat/bar transition point selection for EQ-band mixing."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def build_transition_point_candidates(
    song_analysis: dict[str, Any],
    *,
    role: str,
    strategy_num: int,
    audio_path: str | None = None,
    max_candidates: int = 8,
    min_play_time: float = 45.0,
) -> list[dict[str, Any]]:
    """Return transition point candidates.

    Stem-enhanced transition windows are preferred. If they do not exist, this
    falls back to the MP3-only beat + 4/4 bar method from ``without-stems.md``.
    """
    stem_candidates = build_stem_transition_candidates(
        song_analysis,
        role=role,
        strategy_num=strategy_num,
        max_candidates=max_candidates,
        min_play_time=min_play_time,
    )
    if stem_candidates:
        return stem_candidates
    return build_beat_bar_transition_candidates(
        song_analysis,
        role=role,
        strategy_num=strategy_num,
        audio_path=audio_path,
        max_candidates=max_candidates,
        min_play_time=min_play_time,
    )


def build_stem_transition_candidates(
    song_analysis: dict[str, Any],
    *,
    role: str,
    strategy_num: int,
    max_candidates: int = 8,
    min_play_time: float = 45.0,
) -> list[dict[str, Any]]:
    """Use precomputed stem-aware transition windows as mix entry/exit points."""
    windows = _dict_list(song_analysis.get("transition_windows"))
    if not _has_stem_transition_data(windows, song_analysis):
        return []

    duration = _duration(song_analysis)
    search_start, search_end, prefer_low = _search_range(
        role=role,
        strategy_num=strategy_num,
        duration=duration,
        min_play_time=min_play_time,
    )
    downbeats = _downbeats(song_analysis)
    candidates: list[dict[str, Any]] = []
    for idx, window in enumerate(windows):
        start = _float(window.get("start", window.get("start_sec")), 0.0)
        end = _float(window.get("end", window.get("end_sec")), start)
        point = _snap_to_nearest(start, downbeats, tolerance_sec=1.0)
        if not _in_range(point, search_start, search_end):
            continue

        score_key = "mix_out_score" if role == "outro" else "mix_in_score"
        base_score = _float(window.get(score_key), 0.5)
        energy = _float(window.get("energy"), _sample_energy_at(song_analysis, point))
        position_score = _position_score(point, search_start, search_end)
        energy_score = _energy_score(energy, prefer_low)
        stem_snapshot = _stem_snapshot_for_window(window, song_analysis, start, end)
        vocal = _stem_or_vocal_density(stem_snapshot, song_analysis, start, end)
        low_band = _float(stem_snapshot.get("bass"), _low_band_energy(song_analysis, start, end))

        score = base_score * 0.60 + position_score * 0.15 + energy_score * 0.15
        if vocal < 0.25:
            score += 0.07
        if role == "outro" and "vocal_free" in _tags(window):
            score += 0.05
        if "bass_heavy" in _tags(window):
            score -= 0.05

        candidates.append(
            _candidate(
                role=role,
                label=str(window.get("label") or "stem_window").lower(),
                start=point,
                end=end if end > point else point + _bar_duration(song_analysis),
                priority=score * 100.0,
                energy=energy,
                vocal_density=vocal,
                low_band_energy=low_band,
                downbeats=downbeats,
                source="stem_transition_windows",
                source_detail={
                    "window_index": idx,
                    "mix_score": round(base_score, 4),
                    "stem_tags": _tags(window),
                    "stem_snapshot": {k: round(_float(v, 0.0), 3) for k, v in stem_snapshot.items()},
                },
            )
        )

    return sorted(candidates, key=lambda item: item["priority"], reverse=True)[:max_candidates]


def build_beat_bar_transition_candidates(
    song_analysis: dict[str, Any],
    *,
    role: str,
    strategy_num: int,
    audio_path: str | None = None,
    max_candidates: int = 8,
    min_play_time: float = 45.0,
) -> list[dict[str, Any]]:
    """Select MP3-only bar-aligned transition points.

    The scoring follows ``without-stems.md``: strategy 2 prefers low-energy
    exits and high-energy entries, strategy 3 does the opposite, strategy 5
    uses a neutral energy preference, and all candidates are beat/bar aligned.
    """
    analysis = dict(song_analysis or {})
    loaded = _load_audio_beats(audio_path, role=role) if _needs_audio(analysis) else {}
    beats = _beats(analysis) or _downbeats(analysis) or loaded.get("beats") or []
    if not beats:
        return []

    duration = _duration(analysis) or _float(loaded.get("duration"), 0.0)
    if duration <= 0:
        duration = max(beats) if beats else 0.0
    search_start, search_end, prefer_low = _search_range(
        role=role,
        strategy_num=strategy_num,
        duration=duration,
        min_play_time=min_play_time,
    )
    bars = _bars(analysis, beats)
    energy_lookup = _energy_lookup(analysis, loaded)

    candidates = _score_beat_bar_points(
        points=bars,
        role=role,
        strategy_num=strategy_num,
        search_start=search_start,
        search_end=search_end,
        prefer_low=prefer_low,
        energy_lookup=energy_lookup,
        song_analysis=analysis,
        source="beat_bar",
        bar_aligned=True,
        max_candidates=max_candidates,
    )
    if candidates:
        return candidates

    candidates = _score_beat_bar_points(
        points=beats,
        role=role,
        strategy_num=strategy_num,
        search_start=search_start,
        search_end=search_end,
        prefer_low=prefer_low,
        energy_lookup=energy_lookup,
        song_analysis=analysis,
        source="beat_fallback",
        bar_aligned=False,
        max_candidates=max_candidates,
    )
    if candidates:
        return candidates

    if search_end <= search_start:
        return []
    fallback_time = search_start + (search_end - search_start) * 0.5
    return [
        _candidate(
            role=role,
            label="beat_bar_fallback",
            start=fallback_time,
            end=fallback_time + _bar_duration(analysis, beats),
            priority=1.0,
            energy=0.5,
            vocal_density=_vocal_density(analysis, fallback_time, fallback_time + 4.0, default=0.0),
            low_band_energy=_low_band_energy(analysis, fallback_time, fallback_time + 4.0),
            downbeats=_downbeats(analysis),
            source="beat_bar_fallback",
            source_detail={
                "beat_aligned": False,
                "bar_number": -1,
                "score": 0.0,
            },
        )
    ]


def _score_beat_bar_points(
    *,
    points: list[float],
    role: str,
    strategy_num: int,
    search_start: float,
    search_end: float,
    prefer_low: bool | None,
    energy_lookup,
    song_analysis: dict[str, Any],
    source: str,
    bar_aligned: bool,
    max_candidates: int,
) -> list[dict[str, Any]]:
    if search_end <= search_start:
        return []
    downbeats = _downbeats(song_analysis)
    candidates: list[dict[str, Any]] = []
    for idx, point in enumerate(points):
        if not _in_range(point, search_start, search_end):
            continue
        energy = energy_lookup(point)
        if role == "outro":
            position_score = _position_score(point, search_start, search_end)
            energy_score = _energy_score(energy, prefer_low)
            score = position_score * 0.4 + energy_score * 0.6
        else:
            time_score = 1.0 - _position_score(point, search_start, search_end)
            energy_score = _energy_score(energy, prefer_low)
            score = time_score * 0.5 + energy_score * 0.5
        end = _next_point(points, idx) or point + _bar_duration(song_analysis, points)
        candidates.append(
            _candidate(
                role=role,
                label=_label_at_point(song_analysis, point, default="bar" if bar_aligned else "beat"),
                start=point,
                end=end,
                priority=score * 100.0,
                energy=energy,
                vocal_density=_vocal_density(song_analysis, point, min(end, point + 4.0), default=0.0),
                low_band_energy=_low_band_energy(song_analysis, point, end),
                downbeats=downbeats,
                source=source,
                source_detail={
                    "beat_aligned": True,
                    "bar_aligned": bar_aligned,
                    "bar_number": idx + 1 if bar_aligned else -1,
                    "strategy_num": strategy_num,
                    "score": round(score, 4),
                    "energy": round(energy, 4),
                    "search_range": [round(search_start, 3), round(search_end, 3)],
                },
            )
        )
    return sorted(candidates, key=lambda item: item["priority"], reverse=True)[:max_candidates]


def _candidate(
    *,
    role: str,
    label: str,
    start: float,
    end: float,
    priority: float,
    energy: float,
    vocal_density: float,
    low_band_energy: float,
    downbeats: list[float],
    source: str,
    source_detail: dict[str, Any],
) -> dict[str, Any]:
    start = max(0.0, float(start))
    end = max(start, float(end))
    duration = max(0.0, end - start)
    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(duration, 3),
        "label": label,
        "role": role,
        "energy": round(float(energy), 4),
        "intensity": round(float(energy), 4),
        "priority": round(max(0.0, min(100.0, priority)), 3),
        "priority_reason": source,
        "cue_offset": 0.0,
        "loudness_start": _energy_to_loudness(energy),
        "loudness_end": _energy_to_loudness(energy),
        "vocal_density_start": round(float(vocal_density), 4),
        "vocal_density_end": round(float(vocal_density), 4),
        "vocal_density_avg": round(float(vocal_density), 4),
        "low_band_energy": round(float(low_band_energy), 4),
        "starts_at_downbeat": _is_near(start, downbeats),
        "ends_at_downbeat": _is_near(end, downbeats),
        "tempo": _sample_bpm_at([], start),
        "cut_point_source": source,
        "cut_point_detail": source_detail,
    }


def _load_audio_beats(audio_path: str | None, *, role: str) -> dict[str, Any]:
    if not audio_path or not os.path.isfile(audio_path):
        return {}
    try:
        import librosa
        import numpy as np
    except Exception as exc:  # pragma: no cover - runtime dependency
        logger.warning("[beat-bar] librosa unavailable for %s: %s", audio_path, exc)
        return {}
    try:
        duration_arg = 60 if role == "intro" else None
        y, sr = librosa.load(audio_path, sr=22050, duration=duration_arg)
        if len(y) == 0:
            return {}
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beats, sr=sr)
        rms = librosa.feature.rms(y=y, hop_length=2048)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=2048)
        ref = float(np.percentile(rms, 95)) if len(rms) else 0.0
        energies = [float(min(1.0, max(0.0, value / ref))) if ref > 1e-8 else 0.5 for value in rms]
        return {
            "beats": [float(t) for t in beat_times],
            "duration": float(len(y) / sr),
            "energy_points": list(zip([float(t) for t in times], energies)),
            "tempo": float(tempo[0]) if hasattr(tempo, "__iter__") else float(tempo),
        }
    except Exception as exc:  # pragma: no cover - depends on codec/runtime
        logger.warning("[beat-bar] MP3 beat/bar analysis failed for %s: %s", audio_path, exc)
        return {}


def _search_range(
    *,
    role: str,
    strategy_num: int,
    duration: float,
    min_play_time: float,
) -> tuple[float, float, bool | None]:
    duration = max(0.0, duration)
    if role == "intro":
        if strategy_num == 3:
            return 2.0, min(30.0, max(2.0, duration)), True
        return 2.0, min(30.0 if strategy_num == 2 else 20.0, max(2.0, duration)), False

    if strategy_num == 2:
        return max(min_play_time, duration * 0.5), duration * 0.75, True
    if strategy_num == 3:
        return max(min_play_time, duration * 0.6), duration * 0.9, False
    if strategy_num == 5:
        return max(min_play_time, duration * 0.5), duration * 0.85, None
    return max(min_play_time, duration * 0.55), duration * 0.85, False


def _has_stem_transition_data(windows: list[dict[str, Any]], analysis: dict[str, Any]) -> bool:
    if _dict_list(analysis.get("stem_activity_windows")):
        return True
    for window in windows:
        if window.get("stem_snapshot") or window.get("stem_tags"):
            return True
    return False


def _stem_snapshot_for_window(
    window: dict[str, Any],
    analysis: dict[str, Any],
    start: float,
    end: float,
) -> dict[str, float]:
    raw = window.get("stem_snapshot")
    if isinstance(raw, dict) and raw:
        return {str(k): _float(v, 0.0) for k, v in raw.items()}
    vals = _stem_values_in_range(_dict_list(analysis.get("stem_activity_windows")), start, end)
    return vals


def _stem_values_in_range(windows: list[dict[str, Any]], start: float, end: float) -> dict[str, float]:
    if not windows or end <= start:
        return {}
    keys = ("vocals", "drums", "bass", "other")
    weighted = {key: 0.0 for key in keys}
    total = 0.0
    for window in windows:
        w_start = _float(window.get("start", window.get("start_sec")), 0.0)
        w_end = _float(window.get("end", window.get("end_sec")), w_start)
        overlap = max(0.0, min(end, w_end) - max(start, w_start))
        if overlap <= 0:
            continue
        total += overlap
        for key in keys:
            weighted[key] += _float(window.get(key), 0.0) * overlap
    if total <= 0:
        return {}
    return {key: weighted[key] / total for key in keys}


def _stem_or_vocal_density(
    stem_snapshot: dict[str, float],
    analysis: dict[str, Any],
    start: float,
    end: float,
) -> float:
    if "vocals" in stem_snapshot:
        return max(0.0, min(1.0, _float(stem_snapshot.get("vocals"), 0.0)))
    return _vocal_density(analysis, start, end, default=0.0)


def _vocal_density(analysis: dict[str, Any], start: float, end: float, *, default: float) -> float:
    events = analysis.get("vocal_events") or []
    if isinstance(events, list) and events:
        total = 0.0
        for ev_start, ev_end, confidence in _vocal_event_ranges(events, end):
            overlap = max(0.0, min(end, ev_end) - max(start, ev_start))
            total += overlap * confidence
        return min(1.0, total / (end - start)) if end > start else default
    stems = _stem_values_in_range(_dict_list(analysis.get("stem_activity_windows")), start, end)
    if "vocals" in stems:
        return max(0.0, min(1.0, stems["vocals"]))
    return default


def _vocal_event_ranges(events: list[Any], query_end: float) -> list[tuple[float, float, float]]:
    ranges: list[tuple[float, float, float]] = []
    markers: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if "start" in event or "end" in event:
            start = _float(event.get("start", event.get("time")), 0.0)
            end = _float(event.get("end"), start + _float(event.get("duration"), 0.0))
            if end > start:
                ranges.append((start, end, _float(event.get("confidence"), 1.0)))
        elif "time" in event and "type" in event:
            markers.append(event)
    active_start: float | None = None
    active_confidence = 1.0
    for marker in sorted(markers, key=lambda item: _float(item.get("time"), 0.0)):
        t = _float(marker.get("time"), 0.0)
        kind = str(marker.get("type") or "").lower()
        if kind == "enter":
            active_start = t if active_start is None else active_start
            active_confidence = max(active_confidence, _float(marker.get("confidence"), 1.0))
        elif kind == "exit" and active_start is not None:
            if t > active_start:
                ranges.append((active_start, t, active_confidence))
            active_start = None
            active_confidence = 1.0
    if active_start is not None:
        ranges.append((active_start, max(query_end, active_start), active_confidence))
    return ranges


def _low_band_energy(analysis: dict[str, Any], start: float, end: float) -> float:
    stems = _stem_values_in_range(_dict_list(analysis.get("stem_activity_windows")), start, end)
    if "bass" in stems:
        return max(0.0, min(1.0, stems["bass"]))
    windows = _dict_list(analysis.get("bass_risk_windows"))
    if not windows or end <= start:
        return 0.5
    weighted = 0.0
    total = 0.0
    for window in windows:
        w_start = _float(window.get("start", window.get("start_sec")), 0.0)
        w_end = _float(window.get("end", window.get("end_sec")), w_start)
        overlap = max(0.0, min(end, w_end) - max(start, w_start))
        if overlap <= 0:
            continue
        weighted += overlap * _float(window.get("low_energy", window.get("bass_level", window.get("energy"))), 0.5)
        total += overlap
    return weighted / total if total > 0 else 0.5


def _energy_lookup(analysis: dict[str, Any], loaded: dict[str, Any]):
    energy_points = loaded.get("energy_points") or []

    def lookup(time_sec: float) -> float:
        curve_value = _sample_energy_at(analysis, time_sec, default=None)
        if curve_value is not None:
            return curve_value
        if energy_points:
            nearest = min(energy_points, key=lambda item: abs(float(item[0]) - time_sec))
            return _float(nearest[1], 0.5)
        return 0.5

    return lookup


def _sample_energy_at(analysis: dict[str, Any], time_sec: float, default: float | None = 0.5) -> float | None:
    points: list[tuple[float, float]] = []
    for item in _dict_list(analysis.get("energy_curve")):
        start = _float(item.get("start", item.get("time", item.get("sec"))), 0.0)
        end = _float(item.get("end"), start)
        t = (start + end) * 0.5 if end > start else start
        value = _float(item.get("energy", item.get("relative_energy", item.get("value"))), 0.5)
        points.append((t, value))
    if not points:
        return default
    return max(0.0, min(1.0, min(points, key=lambda point: abs(point[0] - time_sec))[1]))


def _beats(analysis: dict[str, Any]) -> list[float]:
    raw = analysis.get("beat_points") or analysis.get("beats") or []
    if not isinstance(raw, list):
        return []
    out: list[float] = []
    for item in raw:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            continue
    return sorted(t for t in out if t >= 0)


def _bars(analysis: dict[str, Any], beats: list[float]) -> list[float]:
    downbeats = _downbeats(analysis)
    if downbeats:
        return downbeats
    return beats[::4]


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
    return sorted(t for t in out if t >= 0)


def _bar_duration(analysis: dict[str, Any], beats: list[float] | None = None) -> float:
    beat_points = beats or _beats(analysis)
    if len(beat_points) >= 2:
        gaps = [beat_points[i + 1] - beat_points[i] for i in range(min(len(beat_points) - 1, 16))]
        gaps = [gap for gap in gaps if gap > 0]
        if gaps:
            return sum(gaps) / len(gaps) * 4.0
    bpm = _float(analysis.get("bpm"), 120.0)
    return 60.0 / bpm * 4.0 if bpm > 0 else 2.0


def _needs_audio(analysis: dict[str, Any]) -> bool:
    return not (_beats(analysis) or _downbeats(analysis))


def _duration(analysis: dict[str, Any]) -> float:
    duration = _float(analysis.get("duration"), 0.0)
    if duration > 0:
        return duration
    ends = [
        _float(item.get("end", item.get("end_sec")), 0.0)
        for item in _dict_list(analysis.get("phrase_map") or analysis.get("phrases"))
    ]
    return max(ends) if ends else 0.0


def _label_at_point(analysis: dict[str, Any], time_sec: float, *, default: str) -> str:
    for phrase in _dict_list(analysis.get("phrase_map") or analysis.get("phrases")):
        start = _float(phrase.get("start", phrase.get("start_sec")), 0.0)
        end = _float(phrase.get("end", phrase.get("end_sec")), start)
        if start <= time_sec <= end:
            return str(phrase.get("label", phrase.get("type", default)) or default).lower()
    return default


def _next_point(points: list[float], index: int) -> float | None:
    if index + 1 < len(points):
        value = points[index + 1]
        return value if value > points[index] else None
    return None


def _position_score(value: float, start: float, end: float) -> float:
    if end <= start:
        return 0.5
    return max(0.0, min(1.0, (value - start) / (end - start)))


def _energy_score(energy: float, prefer_low: bool | None) -> float:
    energy = max(0.0, min(1.0, float(energy)))
    if prefer_low is True:
        return 1.0 - energy
    if prefer_low is False:
        return energy
    return 0.5


def _in_range(value: float, start: float, end: float) -> bool:
    return end >= start and start <= value <= end


def _snap_to_nearest(time_sec: float, points: list[float], *, tolerance_sec: float) -> float:
    if not points:
        return time_sec
    nearest = min(points, key=lambda point: abs(point - time_sec))
    return nearest if abs(nearest - time_sec) <= tolerance_sec else time_sec


def _is_near(time_sec: float, points: list[float], *, tolerance_sec: float = 0.3) -> bool:
    return any(abs(point - time_sec) <= tolerance_sec for point in points)


def _tags(window: dict[str, Any]) -> list[str]:
    raw = window.get("stem_tags") or []
    return [str(item) for item in raw] if isinstance(raw, list) else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _sample_bpm_at(_: list[Any], __: float) -> float | None:
    return None


def _energy_to_loudness(energy: float) -> float:
    import math

    if energy <= 0:
        return -60.0
    return max(-60.0, min(0.0, 20.0 * math.log10(max(0.001, energy)) - 3.0))


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
