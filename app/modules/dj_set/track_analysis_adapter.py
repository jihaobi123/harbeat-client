"""TrackAnalysisV2 adapter for the DJ set planner.

This module is intentionally read-only: it normalizes the already persisted C1
analysis fields on a LibrarySong-shaped object without trying to re-analyze or
overwrite them. Missing facts are marked as proxy/needs_review so downstream
scorers can distinguish measured evidence from fallback heuristics.
"""
from __future__ import annotations

from typing import Any


def _list(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def _dict(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stem_complete(stems: dict) -> bool:
    return all(bool(stems.get(k)) for k in ("vocals", "drums", "bass", "other"))


def build_track_analysis_v2(song) -> dict:
    """Return the canonical TrackAnalysisV2 dict for planner consumption."""
    stems = _dict(getattr(song, "stems", None))
    stem_quality = _dict(getattr(song, "stem_quality_profile", None))
    beat_points = _list(getattr(song, "beat_points", None))
    phrase_map = _list(getattr(song, "phrase_map", None))
    transition_windows = _list(getattr(song, "transition_windows", None))
    time_signature = _dict(getattr(song, "time_signature", None))

    has_measured_core = bool(getattr(song, "bpm", None)) and bool(beat_points)
    needs_review = bool(getattr(song, "beat_needs_review", False))
    needs_review = needs_review or bool(time_signature.get("needs_review"))
    if needs_review:
        evidence_level = "needs_review"
    elif has_measured_core:
        evidence_level = "measured"
    else:
        evidence_level = "proxy"

    return {
        "schema_version": "track-analysis-v2",
        "track_id": str(getattr(song, "id", "")),
        "title": str(getattr(song, "title", "") or ""),
        "artist": getattr(song, "artist", None),
        "duration_sec": _float(getattr(song, "duration", 0.0)),
        "analysis_version": str(getattr(song, "analysis_version", "") or "2026-06-01.1"),
        "evidence_level": evidence_level,
        "bpm": _float(getattr(song, "bpm", 0.0)),
        "bpm_confidence": _float(getattr(song, "bpm_confidence", None), 1.0 if has_measured_core else 0.4),
        "bpm_curve": _list(getattr(song, "bpm_curve", None)),
        "tempo_stability": _float(getattr(song, "tempo_stability", None), 0.5),
        "beat_points": beat_points,
        "downbeats": _list(getattr(song, "downbeats", None)),
        "time_signature": time_signature,
        "camelot_key": getattr(song, "camelot_key", None),
        "key_confidence": _float(getattr(song, "key_confidence", None), 0.5),
        "energy": _float(getattr(song, "energy", None), 0.5),
        "energy_curve": _list(getattr(song, "energy_curve", None)),
        "loudness_profile": _dict(getattr(song, "loudness_profile", None)),
        "phrase_map": phrase_map,
        "transition_windows": transition_windows,
        "dj_hot_cues": _list(getattr(song, "dj_hot_cues", None)),
        "cue_points": _list(getattr(song, "cue_points", None)),
        "dancefloor_profile": _dict(getattr(song, "dancefloor_profile", None)),
        "genre_profile": _dict(getattr(song, "genre_profile", None)),
        "stems": {
            "available": bool(stems),
            "complete": _stem_complete(stems),
            "quality_score": _float(getattr(song, "stem_quality_score", None), 1.0 if _stem_complete(stems) else 0.0),
            "quality_profile": stem_quality,
            "activity_windows": _list(getattr(song, "stem_activity_windows", None)),
            "vocal_events": _list(getattr(song, "vocal_events", None)),
            "bass_risk_windows": _list(getattr(song, "bass_risk_windows", None)),
        },
    }
