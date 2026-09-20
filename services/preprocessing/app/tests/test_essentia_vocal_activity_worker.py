from __future__ import annotations

import numpy as np

from scripts.essentia_vocal_activity_worker import (
    PLATT_COEFFICIENT,
    PLATT_INTERCEPT,
    VOICE_THRESHOLD,
    build_result,
    calibrate_probabilities,
    merge_activity_ranges,
)


def test_calibration_is_fixed_monotonic_logistic_mapping() -> None:
    raw = np.asarray([0.0, 0.5, 1.0])
    actual = calibrate_probabilities(raw)
    expected = 1.0 / (1.0 + np.exp(-(PLATT_COEFFICIENT * raw + PLATT_INTERCEPT)))
    assert np.allclose(actual, expected)
    assert np.all(np.diff(actual) > 0)


def test_merge_activity_ranges_uses_overlapping_model_windows() -> None:
    ranges = merge_activity_ranges(
        [0.1, VOICE_THRESHOLD, 0.95, 0.2, 0.99], duration_seconds=5.0,
    )
    assert ranges == [
        {"start": 0.93, "end": 2.82},
        {"start": 3.72, "end": 4.68},
    ]


def test_build_result_keeps_density_distinct_from_binary_activity_fraction() -> None:
    result = build_result([0.1, 0.9, 0.95, 0.2], duration_seconds=4.0)
    assert result["vocal_activity_fraction"] == 0.5
    assert 0.0 < result["vocal_density"] < 1.0
    assert result["vocal_density"] != result["vocal_activity_fraction"]
    assert len(result["frames"]) == 4
    assert result["calibration"]["version"] == "jamendo_svd_valid16_platt_v1"
