import json

import numpy as np

from app.modules.library.benchmark_evaluation import (
    binary_metrics,
    dataset_breakdown,
    event_release_gate,
    multilabel_metrics,
    onset_event_metrics,
    select_threshold,
    tempo_metrics,
)


def test_binary_metrics_do_not_hide_false_positives() -> None:
    result = binary_metrics([True, True, False, False], [True, False, True, False])

    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5
    assert result["false_positive"] == 1


def test_binary_metrics_from_numpy_arrays_are_json_serializable() -> None:
    result = binary_metrics(
        np.asarray([True, False]), np.asarray([True, False]),
    )
    assert json.loads(json.dumps(result))["accuracy"] == 1.0


def test_threshold_selection_reports_small_sample_warning() -> None:
    result = select_threshold([(0.9, True), (0.7, True), (0.3, False), (0.1, False)])

    assert 0.3 < result["selected"]["threshold"] <= 0.7
    assert result["selected"]["f1"] == 1.0
    assert result["warning"] == "insufficient_samples_for_release_calibration"


def test_multilabel_metrics_score_each_style_independently() -> None:
    result = multilabel_metrics(
        [{"funk", "disco"}, {"house"}],
        [{"funk"}, {"house", "disco"}],
    )

    assert result["per_label"]["funk"]["recall"] == 1.0
    assert result["per_label"]["disco"]["false_positive"] == 1
    assert result["per_label"]["disco"]["false_negative"] == 1
    assert result["exact_match_ratio"] == 0.0


def test_dataset_breakdown_keeps_provenance_visible() -> None:
    result = dataset_breakdown([
        {"dataset": "mtg_jamendo", "expected_styles": ["funk"]},
        {"dataset": "mtg_jamendo"},
        {"dataset": "groove_midi", "expected_features": {"backbeat": True}},
    ])

    assert result == {
        "groove_midi": {"items": 1, "annotated": 1},
        "mtg_jamendo": {"items": 2, "annotated": 1},
    }


def test_onset_metrics_are_class_aware_and_one_to_one() -> None:
    result = onset_event_metrics(
        {"kick": [0.50, 1.00], "snare": [0.75]},
        {
            "kick": [0.48, 0.51, 1.03],
            # Correct time but wrong class must not match the expected snare.
            "hihat": [{"time": 0.75}],
        },
        tolerance_seconds=0.05,
    )

    assert result["matches"] == 2
    assert result["reference_count"] == 3
    assert result["prediction_count"] == 4
    assert result["per_class"]["kick"]["matches"] == 2
    assert result["per_class"]["kick"]["false_positive"] == 1
    assert result["per_class"]["snare"]["false_negative"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.6667


def test_event_release_gate_requires_enough_events_and_80_percent_scores() -> None:
    passing = event_release_gate({
        "reference_count": 120,
        "precision": 0.84,
        "recall": 0.82,
        "f1": 0.83,
    })
    failing = event_release_gate({
        "reference_count": 80,
        "precision": 0.90,
        "recall": 0.79,
        "f1": 0.84,
    })

    assert passing["passed"] is True
    assert failing["passed"] is False
    assert failing["reasons"] == [
        "insufficient_reference_events",
        "recall_below_gate",
    ]


def test_tempo_metrics_separate_exact_and_metrical_level_correctness() -> None:
    result = tempo_metrics(
        [120.0, 100.0, 90.0, 140.0],
        [121.0, 50.0, 180.0, 100.0],
    )

    assert result["accuracy_1"] == 0.25
    assert result["accuracy_2"] == 0.75
