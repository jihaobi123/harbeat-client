from app.modules.library.benchmark_evaluation import (
    binary_metrics,
    dataset_breakdown,
    multilabel_metrics,
    select_threshold,
)


def test_binary_metrics_do_not_hide_false_positives() -> None:
    result = binary_metrics([True, True, False, False], [True, False, True, False])

    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5
    assert result["false_positive"] == 1


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
