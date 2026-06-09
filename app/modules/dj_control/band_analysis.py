"""Lightweight band-profile helpers for DJ EQ band mixing.

The first eq_band_mix release intentionally avoids stems.  This module derives
coarse low/mid/high density hints from existing LibrarySong analysis fields so
the transition planner can choose safe EQ curves without a new offline pipeline.
"""

from __future__ import annotations

from typing import Any


def clamp01(value: Any, default: float = 0.5) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        x = default
    return max(0.0, min(1.0, x))


def curve_average(curve: Any, default: float = 0.5) -> float:
    """Return a conservative average for JSON curves shaped as dict/list."""
    if not curve:
        return default
    values: list[float] = []
    if isinstance(curve, dict):
        iterable = curve.values()
    elif isinstance(curve, list):
        iterable = curve
    else:
        return default
    for item in iterable:
        if isinstance(item, dict):
            for key in ("value", "energy", "score", "y"):
                if key in item:
                    values.append(clamp01(item[key], default))
                    break
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            values.append(clamp01(item[1], default))
        elif isinstance(item, (int, float)):
            values.append(clamp01(item, default))
    return sum(values) / len(values) if values else default


def band_density(song: Any) -> dict[str, float]:
    """Infer broad band densities from current analysis metadata."""
    music_features = getattr(song, "music_features", None) or {}
    loudness_profile = getattr(song, "loudness_profile", None) or {}
    stem_activity = getattr(song, "stem_activity", None) or {}
    genre_profile = getattr(song, "genre_profile", None) or {}
    energy = clamp01(getattr(song, "energy", None), 0.5)

    low = clamp01(
        music_features.get("low_energy")
        or music_features.get("bass_energy")
        or loudness_profile.get("low")
        or stem_activity.get("bass")
        or genre_profile.get("bass_density"),
        energy,
    )
    mid = clamp01(
        music_features.get("mid_energy")
        or loudness_profile.get("mid")
        or stem_activity.get("vocals")
        or stem_activity.get("other")
        or genre_profile.get("vocal_density"),
        max(0.35, energy * 0.9),
    )
    high = clamp01(
        music_features.get("high_energy")
        or loudness_profile.get("high")
        or genre_profile.get("hi_hat_density"),
        max(0.3, energy * 0.75),
    )
    return {"low": low, "mid": mid, "high": high}
