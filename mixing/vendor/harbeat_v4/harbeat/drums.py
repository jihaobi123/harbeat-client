"""Drum feature similarity helpers."""

from __future__ import annotations

from .models import DrumProfile


def _jaccard(left: set[object], right: set[object], unknown: float = 0.5) -> float:
    if not left and not right:
        return unknown
    union = left | right
    if not union:
        return unknown
    return len(left & right) / len(union)


def drum_overlap_score(left: DrumProfile, right: DrumProfile) -> float:
    """Return a 0.0-1.0 drum overlap score.

    The score mixes timbre/category similarity and core 16-step rhythm overlap.
    Pair-specific analyzer output can override this in higher-level APIs.
    """

    if not left.sound_tags and not left.all_hits and not right.sound_tags and not right.all_hits:
        return 0.0

    sound_score = _jaccard(set(left.sound_tags), set(right.sound_tags))
    rhythm_score = _jaccard(set(left.all_hits), set(right.all_hits))
    return (sound_score * 0.55) + (rhythm_score * 0.45)

