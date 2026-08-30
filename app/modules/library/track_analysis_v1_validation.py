"""Semantic invariants that standard JSON Schema cannot express portably."""
from __future__ import annotations

from math import isclose
from typing import Any


TIME_TOLERANCE_SEC = 0.001
DOWNBEAT_TOLERANCE_SEC = 0.03


def _strictly_increasing(values: list[Any]) -> bool:
    return all(
        isinstance(left, (int, float))
        and isinstance(right, (int, float))
        and not isinstance(left, bool)
        and not isinstance(right, bool)
        and left < right
        for left, right in zip(values, values[1:])
    )


def _same_times(left: list[Any], right: list[Any]) -> bool:
    return len(left) == len(right) and all(
        isinstance(a, (int, float))
        and isinstance(b, (int, float))
        and isclose(float(a), float(b), abs_tol=TIME_TOLERANCE_SEC)
        for a, b in zip(left, right)
    )


def _provenance_refs(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "provenance_ref" and child is not None:
                yield child
            else:
                yield from _provenance_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _provenance_refs(child)


def _bar_missing_paths(bar: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for group_name in ("timing", "structure", "acoustic", "harmony", "rhythm"):
        for feature_name, feature in bar.get(group_name, {}).items():
            if isinstance(feature, dict) and feature.get("availability") != "available":
                paths.append(f"{group_name}.{feature_name}")
    for element_name, element in bar.get("elements", {}).items():
        for feature_name, feature in element.items():
            if isinstance(feature, dict) and feature.get("availability") != "available":
                paths.append(f"elements.{element_name}.{feature_name}")
    return sorted(paths)


def validate_track_analysis_v1_invariants(payload: dict[str, Any]) -> None:
    """Raise ValueError when a TrackAnalysis payload is internally inconsistent."""
    errors: list[str] = []
    analysis_id = payload.get("analysis_id")
    track_id = payload.get("track_id")
    audio = payload.get("audio") or {}
    duration = audio.get("duration_sec")
    timeline = payload.get("timeline") or {}
    bars = payload.get("bars") or []
    beats = timeline.get("beat_times_sec") or []
    downbeats = timeline.get("downbeat_times_sec") or []
    provenance = payload.get("provenance") or {}

    if timeline.get("bar_count") != len(bars):
        errors.append("timeline.bar_count must equal len(bars)")
    if not _strictly_increasing(beats):
        errors.append("timeline.beat_times_sec must be strictly increasing")
    if downbeats and not _strictly_increasing(downbeats):
        errors.append("timeline.downbeat_times_sec must be strictly increasing")
    if isinstance(duration, (int, float)):
        if any(beat < 0 or beat >= duration for beat in beats):
            errors.append("timeline beat lies outside audio duration")
        if any(downbeat < 0 or downbeat >= duration for downbeat in downbeats):
            errors.append("timeline downbeat lies outside audio duration")
    if any(not any(abs(downbeat - beat) <= DOWNBEAT_TOLERANCE_SEC for beat in beats) for downbeat in downbeats):
        errors.append("every downbeat must match a beat within 30 ms")

    flat_bar_beats: list[Any] = []
    expected_beat_start = 0
    for index, bar in enumerate(bars):
        prefix = f"bars[{index}]"
        if bar.get("analysis_id") != analysis_id:
            errors.append(f"{prefix}.analysis_id must match parent")
        if bar.get("track_id") != track_id:
            errors.append(f"{prefix}.track_id must match parent")
        if bar.get("bar_index") != index:
            errors.append(f"{prefix}.bar_index must be contiguous and zero-based")
        if bar.get("beat_start_index") != expected_beat_start:
            errors.append(f"{prefix}.beat_start_index must be contiguous and zero-based")

        bar_beats = (bar.get("timing") or {}).get("beat_times_sec") or []
        if bar.get("beat_count") != len(bar_beats):
            errors.append(f"{prefix}.beat_count must equal len(timing.beat_times_sec)")
        if not _strictly_increasing(bar_beats):
            errors.append(f"{prefix} beat times must be strictly increasing")
        start = bar.get("start_sec")
        end = bar.get("end_sec")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or start >= end:
            errors.append(f"{prefix} must satisfy start_sec < end_sec")
        else:
            if any(beat < start - TIME_TOLERANCE_SEC or beat >= end for beat in bar_beats):
                errors.append(f"{prefix} beat lies outside its half-open interval")
            if index and not isclose(
                float(bars[index - 1].get("end_sec", -1)),
                float(start),
                abs_tol=TIME_TOLERANCE_SEC,
            ):
                errors.append(f"{prefix} must be contiguous with the previous bar")
        expected_missing = _bar_missing_paths(bar)
        actual_missing = sorted((bar.get("quality") or {}).get("missing_fields") or [])
        if actual_missing != expected_missing:
            errors.append(f"{prefix}.quality.missing_fields does not match unavailable features")

        flat_bar_beats.extend(bar_beats)
        expected_beat_start += len(bar_beats)

    if not _same_times(flat_bar_beats, beats):
        errors.append("flattened Bar beat times must equal timeline.beat_times_sec")
    bar_starts = [bar.get("start_sec") for bar in bars]
    if any(not any(isclose(downbeat, start, abs_tol=TIME_TOLERANCE_SEC) for start in bar_starts) for downbeat in downbeats):
        errors.append("every canonical downbeat must be a Bar start")
    if bars and isinstance(duration, (int, float)) and not isclose(
        float(bars[-1].get("end_sec", -1)),
        float(duration),
        abs_tol=TIME_TOLERANCE_SEC,
    ):
        errors.append("last Bar must end at audio duration")

    for segment_index, segment in enumerate(timeline.get("meter_segments") or []):
        start_index = segment.get("start_bar_index")
        end_index = segment.get("end_bar_index")
        numerator = segment.get("numerator")
        if not (
            isinstance(start_index, int)
            and isinstance(end_index, int)
            and isinstance(numerator, int)
            and 0 <= start_index < end_index <= len(bars)
        ):
            errors.append(f"timeline.meter_segments[{segment_index}] has invalid Bar bounds")
            continue
        for bar_index in range(start_index, end_index):
            expected_partial = bars[bar_index].get("beat_count") != numerator
            if bars[bar_index].get("is_partial") != expected_partial:
                errors.append(f"bars[{bar_index}].is_partial disagrees with meter")
            if expected_partial and bar_index not in {0, len(bars) - 1}:
                errors.append(f"bars[{bar_index}] is an interior partial Bar")

    provenance_keys = set(provenance)
    for provenance_ref in _provenance_refs(payload):
        if provenance_ref not in provenance_keys:
            errors.append(f"missing provenance record: {provenance_ref}")

    quality = payload.get("quality") or {}
    expected_feature_sets = sorted(
        {
            path.split(".", 1)[0]
            for bar in bars
            for path in _bar_missing_paths(bar)
        }
    )
    if sorted(quality.get("missing_feature_sets") or []) != expected_feature_sets:
        errors.append("quality.missing_feature_sets does not match Bar missing fields")
    if payload.get("status") == "partial" and not quality.get("needs_review"):
        errors.append("partial TrackAnalysis must set quality.needs_review=true")

    if errors:
        raise ValueError("Invalid TrackAnalysis V1 invariants: " + "; ".join(errors))
