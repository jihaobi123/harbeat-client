from __future__ import annotations

import numpy as np

from app.modules.library.rhythm_feature_analysis import analyze_rhythm_features


def _events_for_steps(steps: list[int], bars: int = 12, bar_length: float = 2.0) -> list[dict]:
    return [
        {"time": bar * bar_length + step / 16 * bar_length, "confidence": 0.9}
        for bar in range(bars) for step in steps
    ]


def _grid(bars: int = 12, bar_length: float = 2.0):
    downbeats = np.arange(0, (bars + 1) * bar_length, bar_length)
    beats = np.arange(0, bars * bar_length, bar_length / 4)
    return beats, downbeats


def test_four_on_floor_and_backbeat_use_explicit_16_step_targets() -> None:
    beats, downbeats = _grid()
    analysis = {
        "events": {
            "kick": _events_for_steps([0, 4, 8, 12]),
            "snare": _events_for_steps([4, 12]),
            "hihat": _events_for_steps([2, 6, 10, 14]),
        }
    }
    result = analyze_rhythm_features(
        analysis, bpm=120, beat_points=beats, downbeats=downbeats, duration=24.0
    )

    assert result["features"]["four_on_floor"]["detected"] is True
    assert result["features"]["backbeat_2_4"]["detected"] is True
    assert result["features"]["two_step"]["detected"] is False
    assert result["features"]["four_on_floor"]["evidence"]["template"]["kick_steps"] == [0, 4, 8, 12]
    assert result["windows"][0]["bar_count"] == 8


def test_dembow_and_tamborzao_are_scored_as_distinct_templates() -> None:
    beats, downbeats = _grid()
    analysis = {
        "events": {
            "kick": _events_for_steps([0, 3, 10]),
            "snare": _events_for_steps([6, 12]),
            "hihat": _events_for_steps([0, 6, 12]),
        }
    }
    result = analyze_rhythm_features(
        analysis, bpm=100, beat_points=beats, downbeats=downbeats, duration=24.0
    )

    assert result["features"]["dembow"]["score"] > result["features"]["tamborzao"]["score"]
    assert result["features"]["dembow"]["detected"] is True
    assert result["features"]["tresillo"]["score"] > 0.0


def test_missing_bar_grid_is_unknown_not_no_rhythm() -> None:
    result = analyze_rhythm_features(
        {"events": {}}, bpm=None, beat_points=[], downbeats=[], duration=20.0
    )

    assert result["status"] == "unavailable"
    assert result["features"]["four_on_floor"]["detected"] is None
