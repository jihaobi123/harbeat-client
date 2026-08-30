from __future__ import annotations

import json
from pathlib import Path

from app.modules.library.style_feature_evidence import (
    STYLE_FEATURE_EVIDENCE_VERSION,
    make_feature_evidence,
    unavailable_feature,
)


def test_available_feature_has_auditable_decision_and_sources() -> None:
    feature = make_feature_evidence(
        0.84,
        threshold=0.65,
        confidence=0.78,
        sources=["bass_stem", "drums_stem", "bass_stem"],
        analysis_method="stft_event_fusion_v1",
        evidence={"fundamental_hz": 54.2},
    )

    assert feature["availability"] == "available"
    assert feature["detected"] is True
    assert feature["evidence_level"] == "confirmed"
    assert feature["sources"] == ["bass_stem", "drums_stem"]
    assert feature["confidence"] == feature["reliability"]
    assert feature["quality"]["measurement_confidence"] == 0.78
    assert feature["quality"]["calibration_status"] == "provisional"


def test_reliability_is_independent_from_match_score() -> None:
    absent = make_feature_evidence(
        0.0,
        confidence=0.9,
        measurement_confidence=0.9,
        source_quality=0.8,
        estimator_quality=0.7,
        sources=["drums_stem"],
        analysis_method="test_fixture",
    )

    assert absent["detected"] is False
    assert absent["reliability"] == 0.82
    assert absent["confidence"] == 0.82


def test_coverage_stability_and_estimator_cap_limit_reliability_not_score() -> None:
    feature = make_feature_evidence(
        0.92,
        confidence=0.95,
        source_quality=0.9,
        estimator_quality=0.9,
        coverage=0.5,
        stability=0.8,
        reliability_cap=0.6,
        raw_measurements={"matched_bars": 8, "bars_analyzed": 16},
        sources=["drums_stem"],
        analysis_method="spectral_proxy",
    )

    assert feature["score"] == 0.92
    assert feature["reliability"] == 0.5834
    assert feature["reliability"] <= 0.6
    assert feature["quality"]["coverage"] == 0.5
    assert feature["quality"]["stability"] == 0.8
    assert feature["evidence"]["raw_measurements"]["matched_bars"] == 8


def test_unavailable_is_unknown_instead_of_negative() -> None:
    feature = unavailable_feature(
        "bass_stem_unavailable",
        sources=["bass_stem"],
        analysis_method="bass_event_analysis_v1",
    )

    assert feature["availability"] == "unavailable"
    assert feature["detected"] is None
    assert feature["score"] is None
    assert feature["evidence_level"] == "unavailable"


def test_v5_schema_describes_quality_calibration_and_unavailable_features() -> None:
    schema_path = (
        Path(__file__).parents[2]
        / "modules/stem-separation/contracts/pre-style-features-v5.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["version"]["const"] == STYLE_FEATURE_EVIDENCE_VERSION
    feature_schema = schema["$defs"]["feature"]
    assert set(feature_schema["required"]) >= {
        "availability", "detected", "score", "reliability", "quality",
        "evidence_level", "sources", "probability", "validation_status",
        "technical_reliability", "style_required_allowed"
    }
