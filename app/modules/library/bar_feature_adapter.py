"""Adapt persisted legacy analysis fields into schema-valid BarFeature V1 rows.

The adapter performs no audio inference. It preserves measured zeroes, marks
missing evidence explicitly, and fails closed when there is no usable beat grid.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable


DEFAULT_PROVENANCE_REF = "prov_legacy_explicit_v1"
DEFAULT_AGGREGATION_PROVENANCE_REF = "prov_bar_aggregation_v1"
TIME_EPSILON_SEC = 1e-6
DOWNBEAT_TOLERANCE_SEC = 0.03
MIN_WINDOW_COVERAGE = 0.95


@dataclass(frozen=True)
class BarInterval:
    start_sec: float
    end_sec: float
    beat_start_index: int
    beat_times_sec: tuple[float, ...]
    is_partial: bool


@dataclass(frozen=True)
class CanonicalTimeline:
    duration_sec: float
    beat_times_sec: tuple[float, ...]
    downbeat_times_sec: tuple[float, ...]
    accepted_downbeat_times_sec: tuple[float, ...]
    numerator: int
    denominator: int
    meter_confidence: float | None
    meter_available: bool
    intervals: tuple[BarInterval, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class WindowAggregate:
    value: float | None
    availability: str
    coverage: float
    warning: str | None = None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _probability(value: Any) -> float | None:
    result = _number(value)
    if result is None:
        return None
    if result < 0.0 or result > 1.0:
        return None
    return round(result, 6)


def _points(values: Any, *, duration: float) -> list[float]:
    if not isinstance(values, (list, tuple)):
        return []
    points = {
        round(point, 6)
        for value in values
        if (point := _number(value)) is not None
        and point >= 0.0
        and point < duration - TIME_EPSILON_SEC
    }
    return sorted(points)


def _meter(song: Any) -> tuple[int, int, float | None, bool]:
    value = getattr(song, "time_signature", None)
    value = value if isinstance(value, dict) else {}
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    valid = (
        isinstance(numerator, int)
        and not isinstance(numerator, bool)
        and 1 <= numerator <= 32
        and denominator in {1, 2, 4, 8, 16, 32}
    )
    if not valid:
        return 4, 4, None, False
    return numerator, denominator, _probability(value.get("confidence")), True


def _align_downbeats(downbeats: Iterable[float], beats: list[float]) -> tuple[list[float], bool]:
    aligned: list[float] = []
    rejected = False
    for downbeat in downbeats:
        nearest = min(beats, key=lambda beat: abs(beat - downbeat))
        if abs(nearest - downbeat) <= DOWNBEAT_TOLERANCE_SEC:
            if not aligned or nearest > aligned[-1] + TIME_EPSILON_SEC:
                aligned.append(nearest)
        else:
            rejected = True
    return aligned, rejected


def build_canonical_timeline(song: Any) -> CanonicalTimeline:
    """Normalize beats, downbeats, meter and Bar intervals exactly once."""
    duration = _number(getattr(song, "duration", None))
    if duration is None or duration <= 0:
        raise ValueError("A positive track duration is required to build the bar timeline")

    beats = _points(getattr(song, "beat_points", None), duration=duration)
    if not beats:
        raise ValueError("A usable beat grid is required to build BarFeature V1")

    numerator, denominator, meter_confidence, meter_available = _meter(song)
    raw_downbeats = _points(getattr(song, "downbeats", None), duration=duration)
    downbeats, rejected_downbeat = _align_downbeats(raw_downbeats, beats)

    warnings: list[str] = []
    if rejected_downbeat:
        warnings.append("DOWNBEAT_OFF_GRID")
    if not meter_available:
        warnings.append("METER_ASSUMED_4_4")

    accepted_downbeats = list(downbeats)
    beat_index = {beat: index for index, beat in enumerate(beats)}
    if downbeats:
        downbeat_indices = [beat_index[downbeat] for downbeat in downbeats]
        anchor = downbeat_indices[0]
        cadence_valid = all((index - anchor) % numerator == 0 for index in downbeat_indices)
        if cadence_valid:
            backward = list(range(anchor, -1, -numerator))[::-1]
            forward = list(range(anchor + numerator, len(beats), numerator))
            canonical_indices = backward + forward
            start_indices = list(canonical_indices)
            if start_indices[0] != 0:
                start_indices.insert(0, 0)
                warnings.append("LEADING_PARTIAL_BAR")
            missing_downbeats = set(canonical_indices) - set(downbeat_indices)
            if missing_downbeats:
                warnings.append("DOWNBEATS_INTERPOLATED")
        else:
            warnings.extend(["DOWNBEAT_CADENCE_INVALID", "TIMELINE_SUSPECT"])
            accepted_downbeats = []
            canonical_indices = list(range(0, len(beats), numerator))
            start_indices = list(canonical_indices)
    else:
        canonical_indices = list(range(0, len(beats), numerator))
        start_indices = list(canonical_indices)
        warnings.append("DOWNBEATS_UNAVAILABLE")

    intervals: list[BarInterval] = []
    starts = [beats[index] for index in start_indices]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else duration
        if end <= start + TIME_EPSILON_SEC:
            continue
        beat_indices = [
            beat_index
            for beat_index, beat in enumerate(beats)
            if beat >= start - TIME_EPSILON_SEC and beat < end - TIME_EPSILON_SEC
        ]
        if not beat_indices:
            raise ValueError(f"Bar interval {start:.6f}-{end:.6f} contains no beat grid point")
        beat_times = tuple(beats[beat_index] for beat_index in beat_indices)
        intervals.append(
            BarInterval(
                start_sec=round(start, 6),
                end_sec=round(end, 6),
                beat_start_index=beat_indices[0],
                beat_times_sec=beat_times,
                is_partial=len(beat_times) != numerator,
            )
        )
    for index, interval in enumerate(intervals):
        is_edge = index in {0, len(intervals) - 1}
        if not is_edge and len(interval.beat_times_sec) != numerator:
            warnings.append("TIMELINE_SUSPECT")

    return CanonicalTimeline(
        duration_sec=round(duration, 6),
        beat_times_sec=tuple(beats),
        downbeat_times_sec=tuple(beats[index] for index in canonical_indices),
        accepted_downbeat_times_sec=tuple(accepted_downbeats),
        numerator=numerator,
        denominator=denominator,
        meter_confidence=meter_confidence,
        meter_available=meter_available,
        intervals=tuple(intervals),
        warnings=tuple(sorted(set(warnings))),
    )


def build_bar_intervals(song: Any) -> tuple[list[BarInterval], list[str]]:
    """Compatibility helper returning intervals and warnings."""
    timeline = build_canonical_timeline(song)
    return list(timeline.intervals), list(timeline.warnings)


def _missing(*, availability: str = "not_computed") -> dict[str, Any]:
    return {
        "value": None,
        "availability": availability,
        "confidence": None,
        "provenance_ref": None,
        "validation_status": "unvalidated",
    }


def _available(value: Any, *, confidence: Any, provenance_ref: str) -> dict[str, Any]:
    return {
        "value": value,
        "availability": "available",
        "confidence": _probability(confidence),
        "provenance_ref": provenance_ref,
        "validation_status": "provisional",
    }


def _weighted_window_value(
    windows: Any,
    key: str,
    start_sec: float,
    end_sec: float,
) -> WindowAggregate:
    if not isinstance(windows, list):
        return WindowAggregate(None, "not_computed", 0.0)
    segments: list[tuple[float, float, float]] = []
    invalid = False
    for window in windows:
        if not isinstance(window, dict) or key not in window:
            continue
        window_start = _number(window.get("start"))
        window_end = _number(window.get("end"))
        value = _number(window.get(key))
        if (
            window_start is None
            or window_end is None
            or value is None
            or window_end <= window_start
            or value < 0.0
            or value > 1.0
        ):
            invalid = True
            continue
        clipped_start = max(start_sec, window_start)
        clipped_end = min(end_sec, window_end)
        if clipped_end <= clipped_start + TIME_EPSILON_SEC:
            continue
        segments.append((clipped_start, clipped_end, value))
    if invalid:
        return WindowAggregate(None, "invalid", 0.0, "INVALID_WINDOW")
    if not segments:
        return WindowAggregate(None, "not_computed", 0.0)

    boundaries = sorted({point for start, end, _value in segments for point in (start, end)})
    weighted_sum = 0.0
    covered_duration = 0.0
    for segment_start, segment_end in zip(boundaries, boundaries[1:]):
        if segment_end <= segment_start + TIME_EPSILON_SEC:
            continue
        midpoint = (segment_start + segment_end) / 2.0
        active_values = [
            value
            for start, end, value in segments
            if start <= midpoint < end
        ]
        if not active_values:
            continue
        duration = segment_end - segment_start
        weighted_sum += (sum(active_values) / len(active_values)) * duration
        covered_duration += duration

    bar_duration = end_sec - start_sec
    coverage = covered_duration / bar_duration if bar_duration > 0 else 0.0
    if coverage + TIME_EPSILON_SEC < MIN_WINDOW_COVERAGE:
        return WindowAggregate(None, "invalid", round(coverage, 6), "PARTIAL_COVERAGE")
    return WindowAggregate(
        round(weighted_sum / covered_duration, 6),
        "available",
        round(coverage, 6),
    )


def _aggregate_feature(aggregate: WindowAggregate, provenance_ref: str) -> dict[str, Any]:
    if aggregate.availability != "available":
        return _missing(availability=aggregate.availability)
    return _available(aggregate.value, confidence=None, provenance_ref=provenance_ref)


def _element(activity: WindowAggregate, provenance_ref: str) -> dict[str, Any]:
    return {
        "state": _missing(),
        "activity": _aggregate_feature(activity, provenance_ref),
        "entry_probability": _missing(),
        "exit_probability": _missing(),
    }


def _missing_paths(bar: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    groups = ("timing", "structure", "acoustic", "harmony", "rhythm")
    for group_name in groups:
        for feature_name, feature in bar[group_name].items():
            if isinstance(feature, dict) and feature.get("availability") != "available":
                paths.append(f"{group_name}.{feature_name}")
    for element_name, element in bar["elements"].items():
        for feature_name, feature in element.items():
            if feature.get("availability") != "available":
                paths.append(f"elements.{element_name}.{feature_name}")
    return sorted(paths)


def build_bar_features(
    song: Any,
    *,
    analysis_id: str,
    provenance_ref: str = DEFAULT_PROVENANCE_REF,
    aggregation_provenance_ref: str = DEFAULT_AGGREGATION_PROVENANCE_REF,
    timeline: CanonicalTimeline | None = None,
) -> list[dict[str, Any]]:
    """Return schema-shaped BarFeature rows without inventing missing values."""
    track_id = str(getattr(song, "id", "") or "")
    if not track_id or not analysis_id:
        raise ValueError("track_id and analysis_id are required")

    timeline = timeline or build_canonical_timeline(song)
    intervals = list(timeline.intervals)
    timeline_warnings = list(timeline.warnings)
    numerator = timeline.numerator
    denominator = timeline.denominator
    meter_confidence = timeline.meter_confidence
    meter_available = timeline.meter_available
    bpm = _number(getattr(song, "bpm", None))
    bpm_confidence = getattr(song, "bpm_confidence", None)
    beat_confidence = _probability(getattr(song, "beat_confidence", None))
    downbeat_confidence = _probability(getattr(song, "downbeat_confidence", None))

    bars: list[dict[str, Any]] = []
    for bar_index, interval in enumerate(intervals):
        stem_windows = getattr(song, "stem_activity_windows", None)
        energy_windows = getattr(song, "energy_curve", None)
        drums = _weighted_window_value(
            stem_windows, "drums", interval.start_sec, interval.end_sec
        )
        vocal = _weighted_window_value(
            stem_windows, "vocals", interval.start_sec, interval.end_sec
        )
        bass = _weighted_window_value(
            stem_windows, "bass", interval.start_sec, interval.end_sec
        )
        energy = _weighted_window_value(
            energy_windows, "energy", interval.start_sec, interval.end_sec
        )

        timing_bpm = (
            _available(round(bpm, 6), confidence=bpm_confidence, provenance_ref=provenance_ref)
            if bpm is not None and bpm > 0
            else _missing(availability="unavailable")
        )
        timing_meter = (
            _available(
                {"numerator": numerator, "denominator": denominator},
                confidence=meter_confidence,
                provenance_ref=provenance_ref,
            )
            if meter_available
            else _missing(availability="unavailable")
        )
        is_accepted_downbeat = any(
            abs(interval.start_sec - downbeat) <= TIME_EPSILON_SEC
            for downbeat in timeline.accepted_downbeat_times_sec
        )
        downbeat_feature = (
            _available(
                downbeat_confidence,
                confidence=None,
                provenance_ref=provenance_ref,
            )
            if is_accepted_downbeat and downbeat_confidence is not None
            else _missing(
                availability="not_computed" if is_accepted_downbeat else "unavailable"
            )
        )

        aggregate_warnings: list[str] = []
        for prefix, aggregate in (
            ("STEM_ACTIVITY", drums),
            ("STEM_ACTIVITY", vocal),
            ("STEM_ACTIVITY", bass),
            ("ENERGY", energy),
        ):
            if aggregate.warning:
                aggregate_warnings.append(f"{prefix}_{aggregate.warning}")

        bar = {
            "schema_name": "harbeat.bar_feature",
            "schema_version": "1.0.0",
            "analysis_id": analysis_id,
            "track_id": track_id,
            "bar_index": bar_index,
            "start_sec": interval.start_sec,
            "end_sec": interval.end_sec,
            "beat_start_index": interval.beat_start_index,
            "beat_count": len(interval.beat_times_sec),
            "is_partial": interval.is_partial,
            "timing": {
                "beat_times_sec": list(interval.beat_times_sec),
                "bpm": timing_bpm,
                "meter": timing_meter,
                "downbeat_confidence": downbeat_feature,
            },
            "structure": {
                "phrase_start_probability": _missing(),
                "phrase_end_probability": _missing(),
                "section_start_probability": _missing(),
                "section_end_probability": _missing(),
                "section_label": _missing(),
            },
            "elements": {
                "drums": _element(drums, aggregation_provenance_ref),
                "vocal": _element(vocal, aggregation_provenance_ref),
                "bass": _element(bass, aggregation_provenance_ref),
                "melody": _element(
                    WindowAggregate(None, "not_computed", 0.0),
                    aggregation_provenance_ref,
                ),
            },
            "acoustic": {
                "energy_normalized": _aggregate_feature(
                    energy, aggregation_provenance_ref
                ),
                "lufs_short_term": _missing(),
                "rms_dbfs": _missing(),
                "sub_energy_ratio": _missing(),
                "bass_energy_ratio": _missing(),
                "mid_energy_ratio": _missing(),
                "high_energy_ratio": _missing(),
            },
            "harmony": {
                "local_key": _missing(),
                "chroma": _missing(),
            },
            "rhythm": {
                "drum_density": _missing(),
                "groove_strength": _missing(),
            },
            "quality": {
                "timeline_confidence": beat_confidence,
                "overall_confidence": None,
                "validation_status": "provisional",
                "needs_review": bool(timeline_warnings or aggregate_warnings),
                "ood_probability": None,
                "missing_fields": [],
                "warnings": sorted(set(timeline_warnings + aggregate_warnings)),
            },
        }
        bar["quality"]["missing_fields"] = _missing_paths(bar)
        bars.append(bar)
    return bars
