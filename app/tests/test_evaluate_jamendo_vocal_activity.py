from __future__ import annotations

from pathlib import Path

import numpy as np

from scripts.evaluate_jamendo_vocal_activity import (
    choose_threshold,
    density_metrics,
    labels_at_centers,
    read_annotations,
    reference_density,
)


def test_annotation_reader_and_patch_center_labels(tmp_path: Path) -> None:
    path = tmp_path / "track.lab"
    path.write_text("0.0 1.0 nosing\n1.0 3.0 sing\n3.0 4.0 nosing\n", encoding="utf-8")
    segments = read_annotations(path)
    assert reference_density(segments) == 0.5
    assert labels_at_centers(4, segments).tolist() == [False, True, True, False]


def test_threshold_selection_uses_only_supplied_rows() -> None:
    rows = [{
        "track": "calibration",
        "raw_probabilities": [0.1, 0.2, 0.9, 0.95],
        "labels": [False, False, True, True],
        "reference_density": 0.5,
    }]
    threshold = choose_threshold(rows)
    assert 0.21 <= threshold <= 0.90


def test_density_metric_reports_song_level_tolerance() -> None:
    rows = [
        {
            "track": "a",
            "raw_probabilities": [0.0, 0.0],
            "labels": [False, False],
            "reference_density": 0.0,
        },
        {
            "track": "b",
            "raw_probabilities": [1.0, 1.0],
            "labels": [True, True],
            "reference_density": 1.0,
        },
    ]
    result = density_metrics(rows, coefficient=20.0, intercept=-10.0)
    assert result["track_count"] == 2
    assert result["within_0_15_fraction"] == 1.0
    assert np.isclose(result["mean_absolute_error"], 0.0, atol=0.001)
