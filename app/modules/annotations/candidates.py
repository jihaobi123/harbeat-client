"""Build reviewable Bar candidates from persisted HarBeat analysis."""
from __future__ import annotations

from math import isfinite
from typing import Any

from app.modules.annotations.public_datasets import map_raveform_section_label
from app.modules.library.bar_feature_adapter import build_bar_features


ELEMENTS = ("drums", "vocal", "bass", "melody")
ACTIVITY_SOURCE = "analysis:stem_activity:v1"
SECTION_SOURCE = "analysis:phrase_map:v1"


def activity_state(value: float | None) -> str:
    """Convert an activity measurement into a review candidate, not ground truth."""
    if value is None:
        return "unknown"
    if value < 0.15:
        return "absent"
    if value < 0.65:
        return "background"
    return "foreground"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _section_candidate(song: Any, start_sec: float, end_sec: float) -> dict[str, Any]:
    best_overlap = 0.0
    best_label: str | None = None
    for phrase in getattr(song, "phrase_map", None) or []:
        if not isinstance(phrase, dict):
            continue
        phrase_start = _number(phrase.get("start", phrase.get("start_sec")))
        phrase_end = _number(phrase.get("end", phrase.get("end_sec")))
        if phrase_start is None or phrase_end is None or phrase_end <= phrase_start:
            continue
        overlap = max(0.0, min(end_sec, phrase_end) - max(start_sec, phrase_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = str(phrase.get("label", ""))
    if best_label is None:
        return {
            "value": "unknown",
            "confidence": None,
            "source": None,
            "source_label": None,
        }
    return {
        "value": map_raveform_section_label(best_label),
        "confidence": None,
        "source": SECTION_SOURCE,
        "source_label": best_label,
    }


def _element_candidate(bar: dict[str, Any], element: str) -> dict[str, Any]:
    feature = bar["elements"][element]["activity"]
    value = feature.get("value") if feature.get("availability") == "available" else None
    return {
        "value": activity_state(value),
        "activity": value,
        "confidence": feature.get("confidence"),
        "source": ACTIVITY_SOURCE if value is not None else None,
    }


def _mark_entry_exit(candidates: list[dict[str, Any]]) -> None:
    for element in ("drums", "vocal", "bass"):
        for index in range(1, len(candidates)):
            previous = candidates[index - 1]["elements"][element]
            current = candidates[index]["elements"][element]
            previous_activity = previous.get("activity")
            current_activity = current.get("activity")
            if previous_activity is None or current_activity is None:
                continue
            if previous_activity < 0.15 and current_activity >= 0.35:
                current["value"] = "entering"
            elif previous_activity >= 0.35 and current_activity < 0.15:
                current["value"] = "ending"


def build_candidate_bars(song: Any) -> list[dict[str, Any]]:
    """Return UI candidates aligned to the canonical Bar timeline."""
    bars = build_bar_features(
        song,
        analysis_id=f"annotation_candidate_{getattr(song, 'id', 'track')}",
    )
    candidates: list[dict[str, Any]] = []
    for bar in bars:
        start_sec = float(bar["start_sec"])
        end_sec = float(bar["end_sec"])
        candidates.append(
            {
                "bar_index": int(bar["bar_index"]),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "beat_times_sec": list(bar["timing"]["beat_times_sec"]),
                "is_partial": bool(bar["is_partial"]),
                "section": _section_candidate(song, start_sec, end_sec),
                "elements": {
                    element: _element_candidate(bar, element)
                    for element in ELEMENTS
                },
            }
        )
    _mark_entry_exit(candidates)
    return candidates
