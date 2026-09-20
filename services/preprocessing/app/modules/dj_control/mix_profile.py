"""Build mix_profile_v1 from existing LibrarySong analysis fields."""

from __future__ import annotations

from typing import Any

from app.modules.dj_control.band_analysis import band_density, clamp01, curve_average


def _float_list(raw: Any, limit: int = 256) -> list[float]:
    if not isinstance(raw, list):
        return []
    values: list[float] = []
    for item in raw[:limit]:
        try:
            values.append(float(item))
        except (TypeError, ValueError):
            continue
    return values


def _phrase_points(song: Any) -> list[float]:
    raw = getattr(song, "phrase_map", None) or []
    points: list[float] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                for key in ("start", "start_sec", "time", "sec"):
                    if key in item:
                        try:
                            points.append(float(item[key]))
                        except (TypeError, ValueError):
                            pass
                        break
            elif isinstance(item, (int, float)):
                points.append(float(item))
    return sorted(set(p for p in points if p >= 0.0))


def _grid_from_bpm(duration: float, bpm: float | None, step_beats: int) -> list[float]:
    if not bpm or bpm <= 0 or duration <= 0:
        return []
    interval = 60.0 / bpm * step_beats
    points: list[float] = []
    t = 0.0
    while t < duration and len(points) < 256:
        points.append(round(t, 3))
        t += interval
    return points


def _safe_points(song: Any, beat_grid: list[float], phrase_grid: list[float]) -> dict[str, list[float]]:
    duration = float(getattr(song, "duration", 0.0) or 0.0)
    cue_points = getattr(song, "cue_points", None) or []
    transition_windows = getattr(song, "transition_windows", None) or []

    mix_in = [p for p in phrase_grid if p <= max(45.0, duration * 0.35)]
    mix_out = [p for p in phrase_grid if duration <= 0 or p >= max(0.0, duration - 75.0)]
    hard_cut = [p for p in phrase_grid if 8.0 <= p <= max(8.0, duration - 8.0)]

    if isinstance(cue_points, list):
        for cue in cue_points:
            if not isinstance(cue, dict):
                continue
            try:
                sec = float(cue.get("sec", cue.get("time", cue.get("start_sec"))))
            except (TypeError, ValueError):
                continue
            label = str(cue.get("label", cue.get("type", ""))).lower()
            if "intro" in label or "in" in label:
                mix_in.append(sec)
            if "outro" in label or "out" in label:
                mix_out.append(sec)
            if "drop" in label or "cut" in label:
                hard_cut.append(sec)

    if isinstance(transition_windows, list):
        for win in transition_windows:
            if not isinstance(win, dict):
                continue
            try:
                start = float(win.get("start_sec", win.get("start", 0.0)))
            except (TypeError, ValueError):
                continue
            kind = str(win.get("type", win.get("label", ""))).lower()
            if "out" in kind:
                mix_out.append(start)
            else:
                mix_in.append(start)

    if not mix_in:
        mix_in = beat_grid[:4] or [0.0]
    if not mix_out:
        mix_out = [p for p in phrase_grid if p >= max(0.0, duration - 64.0)] or [max(0.0, duration - 8.0)]
    if not hard_cut:
        hard_cut = phrase_grid[:8] or beat_grid[:8] or [0.0]

    def uniq(values: list[float]) -> list[float]:
        return sorted({round(max(0.0, v), 3) for v in values})[:16]

    return {
        "mix_in_points": uniq(mix_in),
        "mix_out_points": uniq(mix_out),
        "bass_swap_points": uniq(hard_cut),
        "hard_cut_points": uniq(hard_cut),
    }


def build_mix_profile(song: Any) -> dict[str, Any]:
    """Return doc-shaped mix_profile_v1, synthesized when needed."""
    music_features = getattr(song, "music_features", None) or {}
    existing = music_features.get("mix_profile_v1")
    if isinstance(existing, dict) and existing.get("version") == 1:
        return existing

    duration = float(getattr(song, "duration", 0.0) or 0.0)
    bpm_raw = getattr(song, "bpm", None) or music_features.get("bpm") or music_features.get("tempo")
    try:
        bpm = float(bpm_raw) if bpm_raw is not None else None
    except (TypeError, ValueError):
        bpm = None

    beat_grid = _float_list(getattr(song, "beat_points", None), 256)
    if not beat_grid:
        beat_grid = _grid_from_bpm(duration, bpm, 1)
    downbeat_grid = _float_list(getattr(song, "downbeats", None), 128)
    if not downbeat_grid:
        downbeat_grid = _grid_from_bpm(duration, bpm, 4)
    phrase_grid = _phrase_points(song)
    if not phrase_grid:
        phrase_grid = _grid_from_bpm(duration, bpm, 16) or downbeat_grid

    bands = band_density(song)
    vocal_density = curve_average(getattr(song, "vocal_events", None), default=bands["mid"] * 0.5)
    bass_density = curve_average(getattr(song, "bass_risk_windows", None), default=bands["low"])

    return {
        "version": 1,
        "bpm": bpm,
        "duration_sec": duration,
        "beat_grid": beat_grid,
        "downbeat_grid": downbeat_grid,
        "phrase_grid": phrase_grid,
        "band_energy": {
            "low_curve": [[0.0, round(bands["low"], 3)], [1.0, round(bands["low"], 3)]],
            "mid_curve": [[0.0, round(bands["mid"], 3)], [1.0, round(bands["mid"], 3)]],
            "high_curve": [[0.0, round(bands["high"], 3)], [1.0, round(bands["high"], 3)]],
        },
        "density": {
            "vocal_density_curve": [[0.0, round(clamp01(vocal_density), 3)], [1.0, round(clamp01(vocal_density), 3)]],
            "drum_density_curve": [[0.0, round(clamp01(getattr(song, "has_drum_loop", 0), bands["high"]), 3)]],
            "bass_density_curve": [[0.0, round(clamp01(bass_density), 3)], [1.0, round(clamp01(bass_density), 3)]],
            "high_hat_density_curve": [[0.0, round(bands["high"], 3)], [1.0, round(bands["high"], 3)]],
        },
        "mix_flags": {
            "has_clean_intro": bool(getattr(song, "intro_is_clean", False)),
            "has_drum_intro": bool(getattr(song, "has_drum_loop", False)),
            "has_vocal_intro": bool(vocal_density > 0.55),
            "has_strong_bass_intro": bool(bands["low"] > 0.68),
            "has_usable_outro": bool(getattr(song, "outro_is_clean", False) or duration > 90),
        },
        "safe_points": _safe_points(song, beat_grid, phrase_grid),
    }
