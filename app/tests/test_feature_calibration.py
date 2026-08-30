from __future__ import annotations

from app.modules.library.feature_calibration import (
    apply_feature_calibration,
    calibration_passes_release_gate,
    load_feature_calibration,
)
from app.modules.library.style_feature_evidence import make_feature_evidence, unavailable_feature


def _legacy(score: float = 0.8) -> dict:
    return make_feature_evidence(
        score, threshold=0.6, confidence=0.9,
        sources=["drums_stem"], analysis_method="test_fixture",
    )


def test_uncalibrated_semantic_feature_cannot_be_style_required() -> None:
    feature = apply_feature_calibration(
        _legacy(), group="low_frequency", name="808_timbre_candidate",
        calibration={"version": "feature_calibration_v1", "features": {}},
    )
    assert feature["measurement_score"] == 0.8
    assert feature["probability"] is None
    assert feature["validation_status"] == "candidate_only"
    assert feature["style_required_allowed"] is False


def test_release_gate_requires_accuracy_precision_recall_and_samples() -> None:
    calibration = {
        "version": "feature_calibration_v1",
        "features": {
            "rhythm_grammar.four_on_floor": {
                "status": "validated",
                "style_required_allowed": True,
                "minimum_samples": 50,
                "candidate_threshold": 0.5,
                "confirmed_threshold": 0.8,
                "probability_curve": [[0.0, 0.02], [0.5, 0.55], [1.0, 0.98]],
                "held_out_metrics": {
                    "sample_count": 100, "accuracy": 0.86,
                    "precision": 0.88, "recall": 0.79, "f1": 0.83,
                },
            }
        },
    }
    feature = apply_feature_calibration(
        _legacy(0.9), group="rhythm_grammar", name="four_on_floor",
        calibration=calibration,
    )
    assert feature["validation_status"] == "validated"
    assert feature["probability"] is not None
    assert feature["decision"] == "present"
    assert feature["style_required_allowed"] is True


def test_unavailable_feature_remains_unknown() -> None:
    feature = apply_feature_calibration(
        unavailable_feature("missing", sources=["bass_stem"], analysis_method="test"),
        group="low_frequency", name="sub_bass",
    )
    assert feature["probability"] is None
    assert feature["decision"] == "unknown"
    assert feature["validation_status"] == "unavailable"


def test_repository_calibration_only_releases_heldout_passing_features() -> None:
    calibration = load_feature_calibration()
    released = set()
    for path, entry in calibration["features"].items():
        group, name = path.split(".", 1)
        if calibration_passes_release_gate(entry, group=group, name=name):
            released.add(path)

    assert released == {
        "rhythm_grammar.backbeat_2_4",
        "rhythm_grammar.breakbeat",
        "rhythm_grammar.tamborzao",
        "rhythm_grammar.tresillo",
        "rhythm_grammar.two_step",
        "vocal_delivery.vocal_density",
        "vocal_delivery.vocal_pitch_range",
        "vocal_delivery.pitch_sustain_ratio",
        "vocal_delivery.melodic_contour",
        "harmony.chord_change_activity",
    }


def test_validated_feature_only_releases_the_benchmarked_analysis_method() -> None:
    unsupported = apply_feature_calibration(
        _legacy(0.8), group="vocal_delivery", name="vocal_density",
    )
    supported_input = _legacy(0.8)
    supported_input["analysis_method"] = "vocal_activity_pitch_rhythm_v5"
    supported = apply_feature_calibration(
        supported_input, group="vocal_delivery", name="vocal_density",
    )

    assert unsupported["validation_status"] == "provisional"
    assert unsupported["calibration_method_supported"] is False
    assert supported["validation_status"] == "validated"
    assert supported["calibration_method_supported"] is True


def test_continuous_measurement_can_pass_without_fake_binary_classes() -> None:
    payload = {
        "version": "feature_calibration_v1",
        "features": {
            "vocal_delivery.pitch_sustain_ratio": {
                "status": "validated",
                "validation_mode": "continuous",
                "minimum_samples": 50,
                "minimum_within_tolerance_fraction": 0.80,
                "held_out_metrics": {
                    "sample_count": 100,
                    "within_tolerance_fraction": 0.87,
                    "mean_absolute_error": 0.06,
                },
            },
        },
    }
    result = apply_feature_calibration(
        _legacy(0.72), group="vocal_delivery", name="pitch_sustain_ratio",
        calibration=payload,
    )
    assert result["validation_status"] == "validated"
    assert result["decision"] == "measured"
    assert result["probability"] is None
    assert result["style_required_allowed"] is False


def test_only_semantically_released_validated_feature_can_be_style_required() -> None:
    backbeat = apply_feature_calibration(
        _legacy(0.9), group="rhythm_grammar", name="backbeat_2_4",
    )
    tresillo = apply_feature_calibration(
        _legacy(0.9), group="rhythm_grammar", name="tresillo",
    )
    assert backbeat["validation_status"] == "validated"
    assert backbeat["style_required_allowed"] is True
    assert tresillo["validation_status"] == "validated"
    assert tresillo["validation_scope"] == "transcription_to_rule_only"
    assert tresillo["style_required_allowed"] is False


def test_failed_heldout_feature_is_explicitly_marked_and_never_released() -> None:
    feature = apply_feature_calibration(
        _legacy(0.9), group="percussion_timbre", name="short_rim_snap",
    )

    assert feature["validation_status"] == "failed_validation"
    assert feature["style_required_allowed"] is False
    assert feature["probability"] is None
    assert feature["decision"] == "rejected"


def test_failed_bass_descriptor_cannot_become_style_required() -> None:
    feature = apply_feature_calibration(
        _legacy(0.91), group="low_frequency", name="bass_staccato_ratio",
    )
    assert feature["validation_status"] == "failed_validation"
    assert feature["decision"] == "rejected"
    assert feature["style_required_allowed"] is False
