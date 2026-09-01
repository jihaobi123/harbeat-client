"""Align raw Shadow-model evidence to the canonical Bar timeline."""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.modules.instrument_analysis.schemas import DrumEvent
from app.modules.library.bar_feature_adapter import BarInterval, CanonicalTimeline


EPSILON = 1e-9


@dataclass(frozen=True)
class ProbabilityWindowAggregate:
    mean_probability: float
    max_probability: float
    active_coverage: float
    observed_coverage: float


def _number(mapping: Mapping[str, Any], *names: str) -> float:
    for name in names:
        if name in mapping:
            try:
                return float(mapping[name])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric") from exc
    raise ValueError(f"missing required value: {names[0]}")


def _containing_bar(time_sec: float, timeline: CanonicalTimeline) -> tuple[int, BarInterval]:
    for bar_index, interval in enumerate(timeline.intervals):
        is_last = bar_index == len(timeline.intervals) - 1
        if interval.start_sec <= time_sec < interval.end_sec or (
            is_last and abs(time_sec - interval.end_sec) <= EPSILON
        ):
            return bar_index, interval
    raise ValueError("drum event is outside the canonical timeline")


def align_drum_event(raw_event: Mapping[str, Any], timeline: CanonicalTimeline) -> DrumEvent:
    """Preserve event seconds and add deterministic Bar/Beat coordinates."""
    time_sec = _number(raw_event, "time_sec", "time")
    bar_index, interval = _containing_bar(time_sec, timeline)
    beat_times = tuple(interval.beat_times_sec)
    if not beat_times:
        raise ValueError("containing bar has no beat grid")

    beat_index = max(0, bisect_right(beat_times, time_sec) - 1)
    beat_start = beat_times[beat_index]
    if beat_index + 1 < len(beat_times):
        beat_end = beat_times[beat_index + 1]
    elif len(beat_times) > 1:
        beat_end = min(interval.end_sec, beat_start + (beat_times[-1] - beat_times[-2]))
    else:
        beat_end = interval.end_sec
    duration = max(EPSILON, beat_end - beat_start)
    fraction = min(1.0, max(0.0, (time_sec - beat_start) / duration))

    return DrumEvent(
        time_sec=time_sec,
        drum_class=raw_event.get("drum_class", raw_event.get("class")),
        confidence=_number(raw_event, "confidence", "probability"),
        bar_index=bar_index,
        beat_index_in_bar=beat_index,
        beat_position=round(beat_index + 1.0 + fraction, 6),
    )


def aggregate_probability_windows(
    *,
    windows: Sequence[Mapping[str, Any]],
    bar: Mapping[str, Any] | BarInterval,
    active_threshold: float = 0.5,
) -> ProbabilityWindowAggregate:
    """Aggregate windows by overlap duration rather than window centre."""
    if isinstance(bar, Mapping):
        bar_start = _number(bar, "start_sec", "start")
        bar_end = _number(bar, "end_sec", "end")
    else:
        bar_start = float(bar.start_sec)
        bar_end = float(bar.end_sec)
    if bar_end <= bar_start:
        raise ValueError("bar end must be greater than start")

    segments: list[tuple[float, float, float]] = []
    for window in windows:
        start = _number(window, "start_sec", "start")
        end = _number(window, "end_sec", "end")
        probability = _number(window, "probability", "value")
        if end <= start or not 0.0 <= probability <= 1.0:
            raise ValueError("probability window is invalid")
        clipped_start = max(bar_start, start)
        clipped_end = min(bar_end, end)
        if clipped_end > clipped_start + EPSILON:
            segments.append((clipped_start, clipped_end, probability))

    if not segments:
        return ProbabilityWindowAggregate(0.0, 0.0, 0.0, 0.0)

    boundaries = sorted({point for start, end, _ in segments for point in (start, end)})
    weighted_sum = 0.0
    observed = 0.0
    active = 0.0
    maximum = 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        midpoint = (start + end) / 2.0
        values = [value for left, right, value in segments if left <= midpoint < right]
        if not values:
            continue
        value = sum(values) / len(values)
        duration = end - start
        weighted_sum += value * duration
        observed += duration
        maximum = max(maximum, max(values))
        if value >= active_threshold:
            active += duration

    bar_duration = bar_end - bar_start
    return ProbabilityWindowAggregate(
        mean_probability=round(weighted_sum / observed, 6) if observed else 0.0,
        max_probability=round(maximum, 6),
        active_coverage=round(active / bar_duration, 6),
        observed_coverage=round(observed / bar_duration, 6),
    )
