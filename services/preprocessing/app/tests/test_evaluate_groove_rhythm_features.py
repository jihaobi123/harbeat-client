from scripts.evaluate_groove_rhythm_features import (
    GMD_MIDI_FAMILY,
    _feature_gate,
    summarize_feature_rows,
)


def test_gmd_mapping_preserves_td11_open_and_closed_hat_edges() -> None:
    assert GMD_MIDI_FAMILY[22] == "hihat"
    assert GMD_MIDI_FAMILY[26] == "hihat"
    assert GMD_MIDI_FAMILY[46] == "hihat"


def _feature(detected: bool | None, score: float | None = None) -> dict:
    if detected is None:
        return {"availability": "unavailable", "detected": None, "score": None}
    return {"availability": "available", "detected": detected, "score": score or 0.0}


def test_feature_gate_requires_accuracy_precision_recall_and_class_support() -> None:
    metrics = {
        "sample_count": 50,
        "positive_count": 20,
        "negative_count": 30,
        "accuracy": 0.84,
        "precision": 0.82,
        "recall": 0.75,
        "f1": 0.78,
    }
    assert _feature_gate({**metrics, "f1": 0.80}, available_fraction=0.90)["passed"] is True
    assert _feature_gate({**metrics, "precision": 0.79}, available_fraction=0.90)["passed"] is False


def test_open_hat_is_never_released_from_five_class_worker() -> None:
    rows = [{
        "reference": {"offbeat_open_hat": _feature(True, 0.9)},
        "prediction": {"offbeat_open_hat": _feature(None)},
    } for _ in range(50)]

    result = summarize_feature_rows(rows)["offbeat_open_hat"]

    assert result["release_gate"]["passed"] is False
    assert "worker_does_not_preserve_open_hat_identity" in result["release_gate"]["reasons"]


def test_drill_hat_proxy_cannot_validate_its_semantic_name() -> None:
    rows = []
    for index in range(50):
        expected = index < 20
        rows.append({
            "reference": {"drill_hat": _feature(expected, 0.8 if expected else 0.2)},
            "prediction": {"drill_hat": _feature(expected, 0.8 if expected else 0.2)},
        })

    gate = summarize_feature_rows(rows)["drill_hat"]["release_gate"]

    assert gate["passed"] is False
    assert "dataset_has_no_human_drill_hat_annotation" in gate["reasons"]


def test_summary_reports_score_error_separately_from_binary_accuracy() -> None:
    rows = []
    for index in range(50):
        expected = index < 20
        score = 0.8 if expected else 0.2
        rows.append({
            "reference": {"four_on_floor": _feature(expected, score)},
            "prediction": {"four_on_floor": _feature(expected, score - 0.05)},
        })

    result = summarize_feature_rows(rows)["four_on_floor"]

    assert result["metrics"]["accuracy"] == 1.0
    assert result["mean_absolute_score_error"] == 0.05
    assert result["release_gate"]["passed"] is True
