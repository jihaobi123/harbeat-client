"""Envelope helpers for MP3-only EQ band mix transitions."""

from __future__ import annotations

from typing import Any


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _points(raw: Any) -> list[tuple[float, float]]:
    if not isinstance(raw, list):
        return []
    points: list[tuple[float, float]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                points.append((float(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
    return sorted(points, key=lambda p: p[0])


def eval_curve(raw: Any, beat: float, default: float = 0.0) -> float:
    points = _points(raw)
    if not points:
        return default
    if beat <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if beat <= x1:
            span = max(1e-6, x1 - x0)
            t = max(0.0, min(1.0, (beat - x0) / span))
            return y0 + (y1 - y0) * t
    return points[-1][1]


def _beat_from_keyframe(item: dict[str, Any], fallback: float) -> float:
    for key in ("beat", "beats", "t", "time"):
        parsed = _as_float(item.get(key))
        if parsed is not None:
            return parsed
    return fallback


def _append_keyframe_point(
    curves: dict[str, list[list[float]]],
    item: dict[str, Any],
    beat: float,
    target: str,
    *keys: str,
) -> None:
    for key in keys:
        parsed = _as_float(item.get(key))
        if parsed is not None:
            curves[target].append([beat, parsed])
            return


def _deck_from_keyframes(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, list):
        return None
    curves: dict[str, list[list[float]]] = {
        "fader": [],
        "low": [],
        "mid": [],
        "high": [],
        "cutoff_hz": [],
    }
    filter_type: str | None = None
    fallback_beat = 0.0
    for item in raw:
        if not isinstance(item, dict):
            continue
        beat = _beat_from_keyframe(item, fallback_beat)
        fallback_beat = beat + 1.0
        _append_keyframe_point(curves, item, beat, "fader", "fader", "gain", "volume")
        _append_keyframe_point(curves, item, beat, "low", "low_db", "low")
        _append_keyframe_point(curves, item, beat, "mid", "mid_db", "mid")
        _append_keyframe_point(curves, item, beat, "high", "hi_db", "high_db", "high", "hi")
        filt = item.get("filter")
        if isinstance(filt, dict):
            filter_type = filter_type or str(filt.get("type") or "")
            cutoff = _as_float(filt.get("cutoff_hz"))
        else:
            filter_type = filter_type or str(item.get("filter_type") or "")
            cutoff = _as_float(item.get("cutoff_hz"))
        if cutoff is not None:
            curves["cutoff_hz"].append([beat, cutoff])
    if not any(curves.values()):
        return None
    out: dict[str, Any] = {
        "fader": curves["fader"] or [[0.0, 1.0]],
        "eq": {
            "low": curves["low"] or [[0.0, 0.0]],
            "mid": curves["mid"] or [[0.0, 0.0]],
            "high": curves["high"] or [[0.0, 0.0]],
        },
    }
    if curves["cutoff_hz"]:
        out["filter"] = {
            "type": filter_type or "lowpass",
            "cutoff_hz": curves["cutoff_hz"],
        }
    return out


def eval_deck(deck_plan: dict[str, Any] | list[Any] | None, beat: float) -> dict[str, Any]:
    deck_plan = _deck_from_keyframes(deck_plan) or deck_plan
    if not isinstance(deck_plan, dict):
        deck_plan = {}
    eq = deck_plan.get("eq") if isinstance(deck_plan.get("eq"), dict) else {}
    filter_plan = deck_plan.get("filter") if isinstance(deck_plan.get("filter"), dict) else None
    out = {
        "fader": max(0.0, min(1.5, eval_curve(deck_plan.get("fader"), beat, 1.0))),
        "low_db": max(-60.0, min(12.0, eval_curve(eq.get("low"), beat, 0.0))),
        "mid_db": max(-60.0, min(12.0, eval_curve(eq.get("mid"), beat, 0.0))),
        "hi_db": max(-60.0, min(12.0, eval_curve(eq.get("high"), beat, 0.0))),
        "filter": None,
    }
    if filter_plan:
        cutoff = eval_curve(filter_plan.get("cutoff_hz"), beat, 0.0)
        out["filter"] = {
            "type": str(filter_plan.get("type") or ""),
            "cutoff_hz": max(20.0, min(20000.0, cutoff)) if cutoff else 0.0,
        }
    return out
