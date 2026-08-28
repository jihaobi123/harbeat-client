from __future__ import annotations

import numpy as np

from app.modules.library.rhythm_feature_analysis import (
    _rhythm_boundary_descriptors,
    analyze_rhythm_features,
)


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
    assert {window["bar_count"] for window in result["windows"]} == {4, 8}
    evidence = result["features"]["four_on_floor"]["evidence"]
    assert evidence["global_score"] > 0.9
    assert evidence["stable_window_score"] > 0.9
    assert evidence["best_stable_window"]["window_bars"] in {4, 8}


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


def test_local_pattern_needs_song_coverage_before_detection() -> None:
    beats, downbeats = _grid(bars=16)
    analysis = {
        "events": {
            "kick": _events_for_steps([0, 4, 8, 12], bars=4),
            "snare": _events_for_steps([4, 12], bars=16),
            "hihat": _events_for_steps([2, 6, 10, 14], bars=16),
        }
    }

    result = analyze_rhythm_features(
        analysis, bpm=120, beat_points=beats, downbeats=downbeats, duration=32.0
    )
    feature = result["features"]["four_on_floor"]

    assert feature["evidence"]["stable_window_score"] > feature["evidence"]["global_score"]
    assert feature["evidence"]["stable_song_coverage"] == 0.25
    assert feature["detected"] is False


def test_short_track_uses_four_bar_window_without_becoming_unavailable() -> None:
    beats, downbeats = _grid(bars=4)
    analysis = {
        "events": {
            "kick": _events_for_steps([0, 4, 8, 12], bars=4),
            "snare": _events_for_steps([4, 12], bars=4),
            "hihat": _events_for_steps([2, 6, 10, 14], bars=4),
        }
    }

    result = analyze_rhythm_features(
        analysis, bpm=120, beat_points=beats, downbeats=downbeats, duration=8.0
    )

    assert result["features"]["four_on_floor"]["availability"] == "available"
    assert [window["bar_count"] for window in result["windows"]] == [4]


def test_dense_snare_proxy_does_not_confirm_backbeat_and_halftime_together() -> None:
    beats, downbeats = _grid()
    analysis = {
        "detector_mode": "fallback",
        "confidence": {"overall": 0.58},
        "events": {
            "kick": _events_for_steps([0, 4, 8, 12]),
            "snare": _events_for_steps([0, 4, 8, 12]),
            "hihat": _events_for_steps([0, 2, 4, 6, 8, 10, 12, 14]),
        },
    }

    result = analyze_rhythm_features(
        analysis, bpm=120, beat_points=beats, downbeats=downbeats, duration=24.0
    )
    backbeat = result["features"]["backbeat_2_4"]
    halftime = result["features"]["halftime_snare_3"]

    assert not (backbeat["detected"] and halftime["detected"])
    assert backbeat["reliability"] <= 0.55
    assert halftime["reliability"] <= 0.55
    assert "rhythm_uses_spectral_drum_proxy" in result["quality_flags"]


def test_dance_boundary_features_require_cross_bar_consistency() -> None:
    beats, downbeats = _grid()
    analysis = {
        "detector_mode": "dedicated_model",
        "confidence": {"overall": 0.9},
        "events": {
            "kick": _events_for_steps([0, 4, 8, 12]),
            "snare": _events_for_steps([4, 12]),
            "hihat": [
                {**event, "subtype": "open_hihat"}
                for event in _events_for_steps([2, 6, 10, 14])
            ],
        },
    }

    result = analyze_rhythm_features(
        analysis, bpm=120, beat_points=beats, downbeats=downbeats, duration=24.0,
    )

    assert result["features"]["four_floor_stability"]["score"] > 0.9
    assert result["features"]["offbeat_open_hat"]["score"] > 0.9
    assert result["features"]["timing_quantization"]["score"] > 0.9
    assert result["features"]["drum_loop_repetition"]["score"] > 0.9
    assert result["features"]["offbeat_open_hat"]["evidence"]["explicit_open_hat_event_count"] > 0


def test_open_hat_identity_stays_proxy_limited_without_subtype() -> None:
    beats, downbeats = _grid()
    result = analyze_rhythm_features(
        {
            "detector_mode": "fallback",
            "confidence": {"overall": 0.58},
            "events": {
                "kick": _events_for_steps([0, 4, 8, 12]),
                "snare": _events_for_steps([4, 12]),
                "hihat": _events_for_steps([2, 6, 10, 14]),
            },
        },
        bpm=120, beat_points=beats, downbeats=downbeats, duration=24.0,
    )

    feature = result["features"]["offbeat_open_hat"]
    assert feature["score"] > 0.9
    assert feature["reliability"] <= 0.55
    assert feature["quality"]["calibration_status"] == "hat_family_proxy_only"
    assert "open_hat_subtype_unavailable" in feature["quality_flags"]


def test_boundary_descriptor_penalizes_one_bar_four_floor_fragment() -> None:
    kick = [{0, 4, 8, 12}] + [{0, 7, 13} for _ in range(7)]
    snare = [{4, 12} for _ in range(8)]
    hats = [{2, 6, 10, 14} for _ in range(8)]
    bars = np.arange(0.0, 18.0, 2.0)
    records = [{"time": bar * 2.0 + step / 8.0} for bar in range(8) for step in range(16)]

    result = _rhythm_boundary_descriptors(
        kick=kick, snare=snare, hats=hats, bars=bars, event_records=records,
    )

    assert result["four_floor_bar_coverage"] < 0.3
    assert result["four_floor_stability_score"] < 0.55
