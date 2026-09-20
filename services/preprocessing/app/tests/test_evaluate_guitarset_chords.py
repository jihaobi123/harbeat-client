from __future__ import annotations

from scripts.evaluate_guitarset_chords import (
    activity_score,
    boundary_metrics,
    change_boundaries,
    reduce_chord,
    predicted_activity_score,
)


def test_chord_reduction_respects_model_vocabulary() -> None:
    assert reduce_chord("C:maj/3") == "C:maj"
    assert reduce_chord("D:7") == "D:maj"
    assert reduce_chord("E:min7") == "E:min"
    assert reduce_chord("F#:hdim7") is None
    assert reduce_chord("N") == "N"


def test_change_boundaries_ignore_repeated_labels_and_no_chord() -> None:
    segments = [
        {"start": 0.0, "end": 1.0, "label": "C:maj"},
        {"start": 1.0, "end": 2.0, "label": "C:maj"},
        {"start": 2.0, "end": 3.0, "label": "N"},
        {"start": 3.0, "end": 4.0, "label": "G:maj"},
    ]
    assert change_boundaries(segments) == [3.0]


def test_boundary_matching_is_one_to_one() -> None:
    metrics = boundary_metrics([1.0, 2.0], [0.9, 1.1, 2.2], tolerance=0.25)
    assert metrics["matches"] == 2
    assert metrics["precision"] == 0.6667
    assert metrics["recall"] == 1.0


def test_change_activity_is_per_bar_and_clamped() -> None:
    assert activity_score([1.0, 2.0], 4) == 0.5
    assert activity_score([1.0, 2.0, 3.0, 4.0], 4) == 1.0
    assert activity_score(list(range(20)), 4) == 1.0
    assert predicted_activity_score([1.0, 2.0], 4) == 0.425
