"""Envelope helpers for MP3-only EQ band mix transitions."""

from __future__ import annotations

from typing import Any


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


def eval_deck(deck_plan: dict[str, Any] | None, beat: float) -> dict[str, Any]:
    deck_plan = deck_plan or {}
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
