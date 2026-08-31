"""Build a trusted, half-open Bar timeline from existing beat analysis."""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
import math
import statistics
from typing import Iterable


@dataclass(frozen=True)
class BarWindow:
    index: int
    start_sec: float
    end_sec: float
    beat_start_index: int
    beat_count: int
    is_partial: bool


@dataclass(frozen=True)
class BarTimeline:
    source: str
    meter_numerator: int
    confidence: float
    bars: tuple[BarWindow, ...]


class TimelineError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _clean_points(points: Iterable[float], duration: float) -> list[float]:
    cleaned = {
        float(point)
        for point in points
        if math.isfinite(float(point)) and 0.0 <= float(point) < duration
    }
    return sorted(cleaned)


def build_bar_timeline(
    *,
    downbeats: Iterable[float],
    beat_points: Iterable[float],
    duration: float,
    time_signature: dict | None,
    beat_confidence: float | None,
    beat_needs_review: bool,
) -> BarTimeline:
    """Return trusted Bar windows or an explicit reason the track needs review."""
    if beat_needs_review:
        raise TimelineError("timeline_needs_review", "beat analysis requires review")
    if not math.isfinite(float(duration)) or duration <= 0:
        raise TimelineError("invalid_duration", "song duration must be positive")

    confidence = float(beat_confidence or 0.0)
    if not math.isfinite(confidence) or confidence < 0.5:
        raise TimelineError(
            "low_timeline_confidence",
            "beat confidence is below 0.5",
        )

    signature = time_signature or {}
    meter = int(signature.get("numerator") or 4)
    if meter < 1 or meter > 32:
        raise TimelineError("invalid_meter", "meter numerator is outside 1..32")

    clean_beats = _clean_points(beat_points, duration)
    clean_downbeats = _clean_points(downbeats, duration)
    if len(clean_downbeats) >= 2:
        starts = list(clean_downbeats)
        source = "downbeats"
    else:
        meter_confidence = float(signature.get("confidence") or 0.0)
        if meter_confidence < 0.7 or len(clean_beats) < meter + 1:
            raise TimelineError(
                "missing_trusted_bar_grid",
                "no trusted downbeat or beat-grid fallback",
            )
        starts = clean_beats[::meter]
        source = "beat_grid"

    if starts[0] > 0.05:
        starts.insert(0, 0.0)
    boundaries = starts + ([float(duration)] if starts[-1] < duration else [])
    full_lengths = [
        end - start for start, end in zip(starts, starts[1:]) if end > start
    ]
    typical_length = statistics.median(full_lengths) if full_lengths else float(duration)

    bars: list[BarWindow] = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        if end <= start:
            continue
        beat_start = bisect_left(clean_beats, start - 1e-6)
        beat_end = bisect_left(clean_beats, end - 1e-6)
        bars.append(
            BarWindow(
                index=index,
                start_sec=round(start, 3),
                end_sec=round(end, 3),
                beat_start_index=beat_start,
                beat_count=max(1, beat_end - beat_start),
                is_partial=(end - start) < typical_length * 0.75,
            )
        )

    if not bars:
        raise TimelineError("missing_trusted_bar_grid", "timeline has no Bars")
    return BarTimeline(
        source=source,
        meter_numerator=meter,
        confidence=confidence,
        bars=tuple(bars),
    )
