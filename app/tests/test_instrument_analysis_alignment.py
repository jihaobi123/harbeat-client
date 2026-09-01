import pytest

from app.modules.instrument_analysis.alignment import (
    aggregate_probability_windows,
    align_drum_event,
)
from app.modules.library.bar_feature_adapter import BarInterval, CanonicalTimeline


def timeline_4_4() -> CanonicalTimeline:
    interval = BarInterval(
        start_sec=1.0,
        end_sec=3.0,
        beat_start_index=0,
        beat_times_sec=(1.0, 1.5, 2.0, 2.5),
        is_partial=False,
    )
    return CanonicalTimeline(
        duration_sec=3.0,
        beat_times_sec=interval.beat_times_sec,
        downbeat_times_sec=(1.0,),
        accepted_downbeat_times_sec=(1.0,),
        numerator=4,
        denominator=4,
        meter_confidence=1.0,
        meter_available=True,
        intervals=(interval,),
        warnings=(),
    )


def test_event_keeps_absolute_time_and_fractional_beat_position():
    event = align_drum_event(
        {"time_sec": 1.75, "drum_class": "snare", "confidence": 0.8},
        timeline_4_4(),
    )
    assert event.bar_index == 0
    assert event.beat_index_in_bar == 1
    assert event.beat_position == pytest.approx(2.5)
    assert event.time_sec == 1.75


def test_window_aggregation_keeps_mean_max_and_active_coverage():
    result = aggregate_probability_windows(
        windows=[
            {"start_sec": 0.0, "end_sec": 2.0, "probability": 0.2},
            {"start_sec": 2.0, "end_sec": 4.0, "probability": 0.8},
        ],
        bar={"start_sec": 1.0, "end_sec": 3.0},
    )
    assert result.mean_probability == pytest.approx(0.5)
    assert result.max_probability == pytest.approx(0.8)
    assert result.active_coverage == pytest.approx(0.5)


def test_event_outside_timeline_is_rejected():
    with pytest.raises(ValueError, match="outside"):
        align_drum_event(
            {"time_sec": 0.5, "drum_class": "kick", "confidence": 0.8},
            timeline_4_4(),
        )


def test_window_aggregation_uses_overlap_duration_not_window_centres():
    result = aggregate_probability_windows(
        windows=[
            {"start_sec": 0.0, "end_sec": 1.5, "probability": 1.0},
            {"start_sec": 1.5, "end_sec": 4.0, "probability": 0.0},
        ],
        bar={"start_sec": 1.0, "end_sec": 3.0},
    )
    assert result.mean_probability == pytest.approx(0.25)
    assert result.active_coverage == pytest.approx(0.25)
