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


def _with_model_labels(payload: dict, labels: list[dict]) -> dict:
    payload["model_evidence"] = {
        "status": "ready",
        "routes": {
            "style_tags": {
                "status": "ready",
                "engine": "essentia_discogs_effnet",
                "result": {
                    "model_name": "EffnetDiscogs",
                    "model_version": "1",
                    "aggregation": "0.70*mean+0.30*p75",
                    "labels": labels,
                },
            },
        },
    }
    return payload


def test_house_wins_from_four_floor_electronic_and_metallic_evidence() -> None:
    result = classify_high_frequency_styles(_payload(124, {
        "rhythm_grammar.four_on_floor": 0.96,
        "rhythm_grammar.four_floor_stability": 0.94,
        "rhythm_grammar.offbeat_open_hat": 0.88,
        "rhythm_grammar.timing_quantization": 0.90,
        "rhythm_grammar.drum_loop_repetition": 0.92,
        "rhythm_grammar.drum_machine_consistency": 0.82,
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
    assert result["primary_style"]["style_id"] == "house"
    assert any(item["style_id"] == "house" for item in result["detected_styles"])


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
    assert result["primary_style"] is None
    assert result["detected_styles"] == []


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
        "rhythm_grammar.four_floor_stability": 1.0,
        "rhythm_grammar.offbeat_open_hat": 1.0,
        "rhythm_grammar.timing_quantization": 1.0,
        "rhythm_grammar.drum_loop_repetition": 1.0,
        "rhythm_grammar.drum_machine_consistency": 1.0,
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


def test_disco_requires_more_than_four_floor_and_generic_acoustic_score() -> None:
    result = classify_high_frequency_styles(_payload(120, {
        "rhythm_grammar.four_on_floor": 0.94,
        "rhythm_grammar.backbeat_2_4": 0.75,
        "production.acoustic_production": 0.82,
        "production.brightness": 0.62,
        "low_frequency.kick_bass_alignment": 0.70,
        "percussion_timbre.sustained_metallic": 0.12,
        "low_frequency.low_frequency_melody": 0.10,
        "harmony.chord_change_activity": 0.08,
    }))

    disco = next(item for item in result["styles"] if item["style_id"] == "disco")
    assert disco["required_evidence_ratio"] < 1.0
    assert disco["detected"] is False


def test_auxiliary_model_support_is_bounded_and_keeps_native_score() -> None:
    payload = _with_model_labels(_payload(124, {
        "rhythm_grammar.four_on_floor": 0.93,
        "rhythm_grammar.backbeat_2_4": 0.78,
        "percussion_timbre.sustained_metallic": 0.75,
        "production.electronic_production": 0.82,
        "production.brightness": 0.70,
        "rhythm_grammar.halftime_snare_3": 0.05,
    }), [{"label": "Electronic---House", "score": 0.82}])

    result = classify_high_frequency_styles(payload)
    house = next(item for item in result["styles"] if item["style_id"] == "house")

    assert house["score"] > house["native_score"]
    assert 0.0 < house["model_adjustment"] <= 0.18
    assert house["model_support"]["mapping_type"] == "direct"
    assert result["model_label_evidence"]["raw_labels"][0]["subtype"] == "house"
    assert result["out_of_taxonomy"] is False


def test_unmapped_top_model_label_is_explicitly_out_of_taxonomy() -> None:
    payload = _with_model_labels(_payload(118, {
        "rhythm_grammar.four_on_floor": 0.72,
        "production.electronic_production": 0.65,
        "production.brightness": 0.60,
    }), [{"label": "Pop---K-pop", "score": 0.64}])

    result = classify_high_frequency_styles(payload)

    assert result["out_of_taxonomy"] is True
    assert "top_model_label_outside_or_adjacent_to_21_style_taxonomy" in result["review_reasons"]
    assert result["model_label_evidence"]["unmapped_labels"][0]["subtype"] == "k-pop"


def test_rage_requires_rage_synth_and_distortion_not_generic_bright_electronic_audio() -> None:
    result = classify_high_frequency_styles(_payload(148, {
        "low_frequency.sustained_harmonic_bass_candidate": 0.84,
        "low_frequency.sub_bass": 0.78,
        "production.rage_synth_candidate": 0.18,
        "production.distortion": 0.20,
        "production.brightness": 0.94,
        "production.electronic_production": 0.82,
        "vocal_delivery.rap_delivery": 0.20,
    }))

    rage = next(item for item in result["styles"] if item["style_id"] == "rage")
    assert rage["required_evidence_ratio"] < 1.0
    assert rage["detected"] is False


def test_related_house_model_labels_combine_with_bounded_support() -> None:
    payload = _with_model_labels(_payload(126, {
        "rhythm_grammar.four_on_floor": 0.86,
        "production.electronic_production": 0.78,
        "production.brightness": 0.68,
        "percussion_timbre.sustained_metallic": 0.62,
        "rhythm_grammar.backbeat_2_4": 0.55,
    }), [
        {"label": "Electronic---House", "score": 0.52},
        {"label": "Electronic---Electro House", "score": 0.31},
        {"label": "Electronic---Deep House", "score": 0.18},
    ])

    result = classify_high_frequency_styles(payload)
    house = next(item for item in result["styles"] if item["style_id"] == "house")

    assert house["model_support"]["support"] > 0.52
    assert len(house["model_support"]["sources"]) == 3
    assert house["model_adjustment"] <= 0.18


def test_weak_model_label_is_retained_but_does_not_reorder_native_scores() -> None:
    payload = _with_model_labels(_payload(120, {
        "rhythm_grammar.four_on_floor": 0.90,
        "percussion_timbre.sustained_metallic": 0.72,
        "production.acoustic_production": 0.70,
        "production.brightness": 0.78,
        "low_frequency.kick_bass_alignment": 0.65,
        "low_frequency.low_frequency_melody": 0.62,
        "harmony.chord_change_activity": 0.58,
    }), [{"label": "Electronic---House", "score": 0.06}])

    result = classify_high_frequency_styles(payload)
    house = next(item for item in result["styles"] if item["style_id"] == "house")

    assert house["model_adjustment"] == 0.0
    assert result["model_label_evidence"]["raw_labels"][0]["score"] == 0.06
    assert result["model_label_evidence"]["ignored_low_score_labels"][0]["subtype"] == "house"
