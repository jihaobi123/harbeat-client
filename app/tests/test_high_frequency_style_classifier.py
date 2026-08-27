from __future__ import annotations

from app.modules.library.high_frequency_style_classifier import classify_high_frequency_styles
from app.modules.library.high_frequency_style_taxonomy import STYLE_DEFINITIONS
from app.modules.library.style_feature_evidence import make_feature_evidence, unavailable_feature


def _feature(score: float, confidence: float = 0.9) -> dict:
    return make_feature_evidence(
        score, confidence=confidence, sources=["test"], analysis_method="test_fixture"
    )


def _payload(bpm: float, values: dict[str, float], *, status: str = "ready") -> dict:
    groups = {}
    for path, score in values.items():
        group, name = path.split(".", 1)
        groups.setdefault(group, {})[name] = _feature(score)
    return {
        "version": "pre_style_evidence_v3",
        "status": status,
        "music_context": {"bpm": bpm},
        "feature_groups": groups,
    }


def test_house_wins_from_four_floor_electronic_and_metallic_evidence() -> None:
    result = classify_high_frequency_styles(_payload(124, {
        "rhythm_grammar.four_on_floor": 0.96,
        "rhythm_grammar.backbeat_2_4": 0.80,
        "percussion_timbre.sustained_metallic": 0.84,
        "production.electronic_production": 0.91,
        "production.brightness": 0.72,
        "rhythm_grammar.halftime_snare_3": 0.05,
    }))

    assert result["top_styles"][0]["style_id"] == "house"
    assert result["top_styles"][0]["detected"] is True
    assert result["top_styles"][0]["bpm_fit"] == 1.0
    assert result["decision"]["normalization"] == "absolute_scores_not_forced_to_sum_to_one"
    assert len(result["styles"]) == 21


def test_drill_requires_hat_and_bass_motion_not_merely_generic_trap_808() -> None:
    common = {
        "rhythm_grammar.halftime_snare_3": 0.88,
        "low_frequency.sub_808": 0.90,
        "vocal_delivery.rap_delivery": 0.78,
        "production.dark_timbre": 0.82,
        "rhythm_grammar.four_on_floor": 0.05,
    }
    generic = classify_high_frequency_styles(_payload(140, {
        **common,
        "rhythm_grammar.drill_hat": 0.15,
        "low_frequency.bass_slide": 0.12,
        "low_frequency.sliding_808": 0.05,
        "percussion_timbre.short_metallic": 0.75,
    }))
    drill = classify_high_frequency_styles(_payload(140, {
        **common,
        "rhythm_grammar.drill_hat": 0.93,
        "low_frequency.bass_slide": 0.88,
        "low_frequency.sliding_808": 0.82,
        "percussion_timbre.short_metallic": 0.75,
    }))

    generic_scores = {item["style_id"]: item["score"] for item in generic["styles"]}
    drill_scores = {item["style_id"]: item["score"] for item in drill["styles"]}
    assert generic_scores["trap"] > generic_scores["drill"]
    assert drill_scores["drill"] > drill_scores["trap"]


def test_unavailable_feature_reduces_coverage_instead_of_becoming_negative() -> None:
    payload = _payload(110, {
        "low_frequency.log_drum": 0.92,
        "rhythm_grammar.afro_syncopation": 0.82,
        "percussion_timbre.continuous_high_percussion": 0.74,
    }, status="degraded")
    payload["feature_groups"].setdefault("percussion_timbre", {})["hand_drum_family"] = unavailable_feature(
        "drums_model_unavailable", sources=["drums_stem"], analysis_method="test_fixture"
    )

    result = classify_high_frequency_styles(payload)
    amapiano = next(item for item in result["styles"] if item["style_id"] == "amapiano")

    assert "percussion_timbre.hand_drum_family" in amapiano["missing_evidence"]
    assert all(item["feature"] != "percussion_timbre.hand_drum_family" for item in amapiano["negative_evidence"])
    assert result["needs_review"] is True


def test_missing_v3_features_returns_unavailable_result() -> None:
    result = classify_high_frequency_styles({"version": "pre_style_evidence_v3"})

    assert result["status"] == "unavailable"
    assert result["top_styles"] == []


def test_each_style_rule_can_win_from_its_own_complete_evidence_signature() -> None:
    for style_id, rule in STYLE_DEFINITIONS.items():
        values = {path: 1.0 for path in rule["positive"]}
        values.update({path: 0.0 for path in rule["negative"]})
        low, high = rule["bpm_ranges"][0]
        result = classify_high_frequency_styles(_payload((low + high) / 2, values))

        assert result["top_styles"][0]["style_id"] == style_id
