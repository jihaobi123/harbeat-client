from __future__ import annotations

import json
from pathlib import Path

from app.modules.library.style_feature_evidence import (
    STYLE_FEATURE_EVIDENCE_VERSION,
    from_v2_feature,
    make_feature_evidence,
    to_v2_feature,
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


def test_v2_adapter_preserves_available_evidence_and_marks_missing_input() -> None:
    available = from_v2_feature(
        {
            "detected": True,
            "score": 0.7,
            "decision_threshold": 0.55,
            "confidence": 0.65,
            "time_ranges": [{"start": 1.0, "end": 1.2}],
            "evidence": {"candidate_count": 3},
        },
        sources=["drums_stem"],
        analysis_method="legacy_proxy_v2",
    )
    missing = from_v2_feature(
        {"detected": False, "score": 0.0, "confidence": 0.0, "evidence": {}},
        sources=["bass_stem"],
        analysis_method="legacy_proxy_v2",
    )

    assert available["detected"] is True
    assert available["evidence"]["candidate_count"] == 3
    assert to_v2_feature(available)["detected"] is True
    assert missing["detected"] is None
    assert to_v2_feature(missing)["evidence"]["availability"] == "unavailable"


def test_v3_schema_describes_available_and_unavailable_features() -> None:
    schema_path = (
        Path(__file__).parents[2]
        / "modules/stem-separation/contracts/pre-style-features-v3.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["version"]["const"] == STYLE_FEATURE_EVIDENCE_VERSION
    feature_schema = schema["$defs"]["feature"]
    assert set(feature_schema["required"]) >= {
        "availability", "detected", "score", "evidence_level", "sources"
    }
    unavailable_rule = feature_schema["allOf"][0]["then"]["properties"]
    assert unavailable_rule["detected"]["type"] == "null"
    assert unavailable_rule["score"]["type"] == "null"
