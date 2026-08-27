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
        "version": "pre_style_evidence_v4",
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
        "low_frequency.sustained_harmonic_bass_candidate": 0.90,
        "low_frequency.808_timbre_candidate": 0.70,
        "vocal_delivery.rap_delivery": 0.78,
        "production.dark_timbre": 0.82,
        "rhythm_grammar.four_on_floor": 0.05,
    }
    generic = classify_high_frequency_styles(_payload(140, {
        **common,
        "rhythm_grammar.drill_hat": 0.15,
        "low_frequency.bass_slide": 0.12,
        "low_frequency.sliding_bass_candidate": 0.05,
        "percussion_timbre.short_metallic": 0.75,
    }))
    drill = classify_high_frequency_styles(_payload(140, {
        **common,
        "rhythm_grammar.drill_hat": 0.93,
        "low_frequency.bass_slide": 0.88,
        "low_frequency.sliding_bass_candidate": 0.82,
        "percussion_timbre.short_metallic": 0.75,
    }))

    generic_scores = {item["style_id"]: item["score"] for item in generic["styles"]}
    drill_scores = {item["style_id"]: item["score"] for item in drill["styles"]}
    assert generic_scores["trap"] > generic_scores["drill"]
    assert drill_scores["drill"] > drill_scores["trap"]


def test_trap_soul_is_suppressed_by_four_floor_without_independent_808_timbre() -> None:
    common = {
        "vocal_delivery.singing": 0.84,
        "rhythm_grammar.halftime_snare_3": 0.76,
        "low_frequency.sustained_harmonic_bass_candidate": 0.82,
        "harmony.jazz_soul_harmony": 0.45,
    }
    disco_like = classify_high_frequency_styles(_payload(122, {
        **common,
        "low_frequency.808_timbre_candidate": 0.18,
        "production.dark_timbre": 0.20,
        "rhythm_grammar.four_on_floor": 0.94,
    }))
    trap_soul_like = classify_high_frequency_styles(_payload(74, {
        **common,
        "low_frequency.808_timbre_candidate": 0.86,
        "production.dark_timbre": 0.72,
        "rhythm_grammar.four_on_floor": 0.08,
    }))

    disco_score = next(item for item in disco_like["styles"] if item["style_id"] == "trap_soul")
    trap_soul_score = next(item for item in trap_soul_like["styles"] if item["style_id"] == "trap_soul")
    assert disco_score["required_evidence_ratio"] < 1.0
    assert trap_soul_score["required_evidence_ratio"] == 1.0
    assert trap_soul_score["score"] > disco_score["score"] + 0.20


def test_unavailable_feature_reduces_coverage_instead_of_becoming_negative() -> None:
    payload = _payload(110, {
        "low_frequency.low_percussive_bass_candidate": 0.92,
        "low_frequency.bass_reply_pattern": 0.88,
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


def test_missing_v4_features_returns_unavailable_result() -> None:
    result = classify_high_frequency_styles({"version": "pre_style_evidence_v4"})

    assert result["status"] == "unavailable"
    assert result["top_styles"] == []


def test_each_style_rule_can_win_from_its_own_complete_evidence_signature() -> None:
    for style_id, rule in STYLE_DEFINITIONS.items():
        values = {path: 1.0 for path in rule["positive"]}
        values.update({path: 0.0 for path in rule["negative"]})
        low, high = rule["bpm_ranges"][0]
        result = classify_high_frequency_styles(_payload((low + high) / 2, values))

        assert result["top_styles"][0]["style_id"] == style_id


def test_style_confidence_is_capped_by_feature_reliability() -> None:
    payload = _payload(124, {
        "rhythm_grammar.four_on_floor": 1.0,
        "rhythm_grammar.backbeat_2_4": 1.0,
        "percussion_timbre.sustained_metallic": 1.0,
        "production.electronic_production": 1.0,
        "production.brightness": 1.0,
    })
    for group in payload["feature_groups"].values():
        for feature in group.values():
            feature["reliability"] = 0.60
            feature["confidence"] = 0.60
            feature["quality"] = {
                "measurement_confidence": 0.8,
                "source_quality": 0.7,
                "estimator_quality": 0.6,
                "calibration_status": "provisional",
            }

    result = classify_high_frequency_styles(payload)
    house = next(item for item in result["styles"] if item["style_id"] == "house")

    assert house["score"] > 0.6
    assert house["reliability"] <= 0.60
    assert house["confidence"] <= house["reliability"]
    assert house["quality"]["estimator_quality"] == 0.6
