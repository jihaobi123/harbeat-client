"""Explainable scoring and review gates for the 21-style taxonomy."""
from __future__ import annotations

from typing import Any

import numpy as np

from app.modules.library.high_frequency_style_taxonomy import (
    STYLE_DEFINITIONS,
    STYLE_GROUPS,
    STYLE_TAXONOMY_VERSION,
)


STYLE_ANALYSIS_VERSION = "high_frequency_style_analysis_v4"
MODEL_ROUTE_SUPPORT_FLOOR = 0.10
MODEL_LABEL_COMPONENT_FLOOR = 0.02
BOUNDARY_PAIR_MAX_GAP = 0.10
BOUNDARY_TOTAL_ADJUSTMENT_CAP = 0.08


BOUNDARY_PROFILES = {
    ("funk", "disco"): (
        {
            "low_frequency.bass_syncopation": 1.2,
            "low_frequency.bass_staccato_ratio": 0.9,
            "low_frequency.bass_kick_interlock": 0.8,
            "rhythm_grammar.backbeat_2_4": 0.5,
        },
        {
            "low_frequency.bass_octave_pattern": 1.2,
            "rhythm_grammar.four_floor_stability": 1.0,
            "rhythm_grammar.offbeat_open_hat": 0.9,
        },
    ),
    ("funk", "house"): (
        {
            "low_frequency.bass_syncopation": 1.2,
            "low_frequency.bass_staccato_ratio": 0.9,
            "low_frequency.bass_kick_interlock": 0.8,
            "production.acoustic_production": 0.4,
        },
        {
            "rhythm_grammar.timing_quantization": 1.0,
            "rhythm_grammar.drum_loop_repetition": 0.9,
            "rhythm_grammar.drum_machine_consistency": 0.8,
            "production.electronic_production": 0.7,
        },
    ),
    ("disco", "house"): (
        {
            "low_frequency.bass_octave_pattern": 1.2,
            "production.acoustic_production": 0.5,
            "harmony.chord_change_activity": 0.4,
        },
        {
            "rhythm_grammar.timing_quantization": 1.0,
            "rhythm_grammar.drum_machine_consistency": 0.9,
            "production.electronic_production": 0.8,
        },
    ),
}

# Explicit label bridges for the optional Discogs/open-label route.  Exact or
# close musical synonyms are direct; broader neighbouring subgenres are marked
# adjacent so the result remains reviewable instead of pretending the 21-class
# taxonomy covered the raw label exactly.
MODEL_STYLE_LABEL_RULES = {
    "boombap": (("boom bap", "boom-bap"), ("instrumental hip hop",)),
    "trap": (("trap",), ("cloud rap",)),
    "funk": (("funk", "g-funk", "p.funk", "electro-funk"), ("boogie",)),
    "breakbeat": (("breakbeat", "breaks"), ("big beat",)),
    "soul_neo_soul": (("neo soul", "soul"), ("contemporary r&b",)),
    "jazz_hiphop": (("jazz rap",), ("instrumental hip hop",)),
    "afro_afrobeats": (("afrobeat", "afrobeats"), ("afro house",)),
    "house": (("house",), (
        "euro house", "garage house", "italo house", "hip-house", "electro house",
        "progressive house", "tropical house", "deep house", "ghetto house",
        "tech house", "tribal house", "acid house",
    )),
    "grime_uk_hiphop": (("grime", "uk hip hop"), ("bassline",)),
    "rnb": (("rhythm & blues", "r&b"), ("contemporary r&b",)),
    "disco": (("disco", "nu-disco", "post-disco", "italo-disco", "space disco"), ("boogie", "dance-pop", "eurodance")),
    "jersey_club": (("jersey club",), ()),
    "drill": (("drill",), ("uk drill",)),
    "amapiano": (("amapiano",), ()),
    "moombahton": (("moombahton",), ()),
    "dancehall": (("dancehall",), ("ragga",)),
    "baile_funk": (("baile funk", "funk carioca"), ()),
    "memphis_trap": (("memphis rap",), ("phonk",)),
    "rage": (("rage",), ("rage rap",)),
    "uk_garage": (("uk garage", "2-step", "speed garage"), ("garage house",)),
    "trap_soul": (("trap soul",), ("alternative r&b",)),
}

FEATURE_COMPATIBILITY_ALIASES = {
    "low_frequency.sustained_harmonic_bass_candidate": "low_frequency.sub_808",
    "low_frequency.808_timbre_candidate": "low_frequency.sub_808",
    "low_frequency.sliding_bass_candidate": "low_frequency.sliding_808",
    "low_frequency.low_percussive_bass_candidate": "low_frequency.log_drum",
    "vocal_delivery.vocal_chop_repetition": "vocal_delivery.vocal_chop",
    "production.rage_synth_candidate": "production.rage_synth",
}


def _clamp(value: float) -> float:
    return float(np.clip(float(value), 0.0, 1.0))


def _feature(groups: dict, path: str) -> dict[str, Any] | None:
    group, name = path.split(".", 1)
    value = (groups.get(group) or {}).get(name)
    if not isinstance(value, dict) and path in FEATURE_COMPATIBILITY_ALIASES:
        legacy_group, legacy_name = FEATURE_COMPATIBILITY_ALIASES[path].split(".", 1)
        value = (groups.get(legacy_group) or {}).get(legacy_name)
    return value if isinstance(value, dict) else None


def _available(feature: dict | None) -> bool:
    if not feature:
        return False
    if "availability" in feature:
        return feature.get("availability") == "available" and feature.get("score") is not None
    return feature.get("score") is not None and float(feature.get("confidence", 0.0) or 0.0) > 0


def _effective(feature: dict) -> tuple[float, float, float]:
    score = _clamp(feature.get("score", 0.0) or 0.0)
    confidence = _clamp(feature.get("reliability", feature.get("confidence", 0.0)) or 0.0)
    # Confidence discounts uncertain evidence but never silently changes the
    # underlying acoustic score shown to the reviewer.
    effective = score * (0.55 + 0.45 * confidence)
    return score, confidence, effective


def _bpm_fit(bpm: float | None, ranges: list[list[float]]) -> tuple[float, bool]:
    if bpm is None or not np.isfinite(bpm) or bpm <= 0:
        return 0.5, False
    value = float(bpm)
    if any(low <= value <= high for low, high in ranges):
        return 1.0, True
    distance = min(min(abs(value - low), abs(value - high)) for low, high in ranges)
    return _clamp(1.0 - distance / 18.0), True


def _evidence_item(path: str, feature: dict, weight: float, contribution: float) -> dict[str, Any]:
    score, confidence, _ = _effective(feature)
    return {
        "feature": path,
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "reliability": round(confidence, 4),
        "quality": dict(feature.get("quality") or {}),
        "weight": round(float(weight), 4),
        "contribution": round(float(contribution), 4),
        "evidence_level": feature.get("evidence_level", "unavailable"),
        "time_ranges": list(feature.get("time_ranges") or [])[:12],
    }


def _score_style(style_id: str, rule: dict[str, Any], groups: dict, bpm: float | None) -> dict[str, Any]:
    positive_weight_total = float(sum(rule["positive"].values()))
    available_weight = 0.0
    weighted_positive = 0.0
    confidence_weighted = 0.0
    quality_weighted = {
        "measurement_confidence": 0.0,
        "source_quality": 0.0,
        "estimator_quality": 0.0,
    }
    positive_evidence = []
    missing = []
    evidence_count = 0
    for path, weight in rule["positive"].items():
        feature = _feature(groups, path)
        if not _available(feature):
            missing.append(path)
            continue
        score, confidence, effective = _effective(feature)
        available_weight += weight
        weighted_positive += weight * effective
        confidence_weighted += weight * confidence
        quality = feature.get("quality") or {}
        for name in quality_weighted:
            quality_weighted[name] += weight * _clamp(quality.get(name, confidence) or 0.0)
        if score >= 0.35:
            evidence_count += 1
            positive_evidence.append(_evidence_item(path, feature, weight, weight * effective))

    positive_score = weighted_positive / max(available_weight, 1e-8)
    coverage = available_weight / max(positive_weight_total, 1e-8)
    evidence_confidence = confidence_weighted / max(available_weight, 1e-8)
    quality_profile = {
        name: value / max(available_weight, 1e-8)
        for name, value in quality_weighted.items()
    }

    negative_evidence = []
    negative_total = float(sum(rule["negative"].values()))
    negative_value = 0.0
    for path, weight in rule["negative"].items():
        feature = _feature(groups, path)
        if not _available(feature):
            continue
        score, _, effective = _effective(feature)
        negative_value += weight * effective
        if score >= 0.35:
            negative_evidence.append(_evidence_item(path, feature, weight, weight * effective))
    negative_score = negative_value / max(negative_total, 1e-8) if negative_total else 0.0

    requirements = []
    for alternatives in rule["required_any"]:
        candidates = []
        for path in alternatives:
            feature = _feature(groups, path)
            if _available(feature):
                score, confidence, effective = _effective(feature)
                candidates.append((effective, path, score, confidence))
        best = max(candidates, default=(0.0, None, 0.0, 0.0))
        requirements.append({
            "alternatives": alternatives,
            "satisfied": best[0] >= float(rule.get("requirement_threshold", 0.46)),
            "best_feature": best[1],
            "best_effective_score": round(float(best[0]), 4),
        })
    required_ratio = (
        sum(item["satisfied"] for item in requirements) / len(requirements)
        if requirements else 1.0
    )
    bpm_score, bpm_available = _bpm_fit(bpm, rule["bpm_ranges"])
    evidence_sufficiency = _clamp(evidence_count / max(rule["minimum_evidence"], 1))
    base = (
        0.62 * positive_score
        + 0.16 * bpm_score
        + 0.14 * required_ratio
        + 0.08 * evidence_sufficiency
    )
    coverage_factor = 0.48 + 0.52 * coverage
    final_score = _clamp(base * coverage_factor - 0.28 * negative_score)
    reliability = _clamp(
        evidence_confidence
        * (0.60 + 0.40 * coverage)
        * (0.85 + 0.15 * required_ratio)
    )
    confidence = min(final_score, reliability)
    positive_evidence.sort(key=lambda item: item["contribution"], reverse=True)
    negative_evidence.sort(key=lambda item: item["contribution"], reverse=True)
    return {
        "style_id": style_id,
        "name": rule["name"],
        "group": rule["group"],
        "score": round(final_score, 4),
        "confidence": round(confidence, 4),
        "reliability": round(reliability, 4),
        "quality": {
            **{name: round(value, 4) for name, value in quality_profile.items()},
            "feature_coverage": round(coverage, 4),
            "calibration_status": "provisional",
        },
        "detected": bool(
            final_score >= 0.55 and reliability >= 0.45
            and required_ratio >= 1.0 and evidence_count >= rule["minimum_evidence"]
        ),
        "bpm_fit": round(bpm_score, 4),
        "bpm_available": bpm_available,
        "bpm_ranges": rule["bpm_ranges"],
        "feature_coverage": round(coverage, 4),
        "evidence_count": evidence_count,
        "minimum_evidence": rule["minimum_evidence"],
        "required_evidence_ratio": round(required_ratio, 4),
        "requirement_threshold": round(float(rule.get("requirement_threshold", 0.46)), 4),
        "requirements": requirements,
        "positive_evidence": positive_evidence,
        "negative_evidence": negative_evidence,
        "missing_evidence": missing,
    }


def _normalized_model_subtype(label: str) -> str:
    subtype = str(label).split("---", 1)[-1]
    return " ".join(subtype.lower().replace("_", " ").split())


def _model_label_mapping(features: dict[str, Any]) -> dict[str, Any]:
    route = (((features.get("model_evidence") or {}).get("routes") or {}).get("style_tags") or {})
    if route.get("status") != "ready":
        return {
            "status": "unavailable",
            "engine": route.get("engine"),
            "raw_labels": [],
            "mapped_styles": {},
            "unmapped_labels": [],
            "ignored_low_score_labels": [],
            "out_of_taxonomy": False,
        }
    raw_labels = (route.get("result") or {}).get("labels") or []
    peak_score = _clamp(
        raw_labels[0].get("score", 0.0) or 0.0
    ) if raw_labels and isinstance(raw_labels[0], dict) else 0.0
    route_support_enabled = peak_score >= MODEL_ROUTE_SUPPORT_FLOOR
    normalized_labels = []
    mapped_candidates: dict[str, list[dict[str, Any]]] = {}
    unmapped = []
    ignored_low_score = []
    for item in raw_labels[:25]:
        if not isinstance(item, dict) or not item.get("label"):
            continue
        score = _clamp(item.get("score", 0.0) or 0.0)
        raw_label = str(item["label"])
        subtype = _normalized_model_subtype(raw_label)
        normalized = {"label": raw_label, "subtype": subtype, "score": round(score, 4)}
        normalized_labels.append(normalized)
        if not route_support_enabled or score < MODEL_LABEL_COMPONENT_FLOOR:
            ignored_low_score.append(normalized)
            continue
        candidates = []
        for style_id, (direct_terms, adjacent_terms) in MODEL_STYLE_LABEL_RULES.items():
            if subtype in direct_terms:
                candidates.append((style_id, "direct", 1.0))
            elif subtype in adjacent_terms:
                candidates.append((style_id, "adjacent", 0.60))
        if not candidates:
            unmapped.append(normalized)
            continue
        for style_id, mapping_type, mapping_weight in candidates:
            support = score * mapping_weight
            mapped_candidates.setdefault(style_id, []).append({
                    "weighted_support": support,
                    "mapping_type": mapping_type,
                    "raw_label": raw_label,
                    "raw_score": round(score, 4),
            })
    mapped = {}
    for style_id, sources in mapped_candidates.items():
        sources.sort(key=lambda value: value["weighted_support"], reverse=True)
        combined_support = 1.0 - float(np.prod([
            1.0 - _clamp(value["weighted_support"]) for value in sources
        ]))
        mapped[style_id] = {
            "support": round(combined_support, 4),
            "mapping_type": "direct" if any(
                value["mapping_type"] == "direct" for value in sources
            ) else "adjacent",
            "raw_label": sources[0]["raw_label"],
            "raw_score": sources[0]["raw_score"],
            "sources": [
                {
                    "raw_label": value["raw_label"],
                    "raw_score": value["raw_score"],
                    "mapping_type": value["mapping_type"],
                    "weighted_support": round(value["weighted_support"], 4),
                }
                for value in sources[:8]
            ],
        }
    top_raw = normalized_labels[0] if normalized_labels else None
    top_mappings = [
        source
        for value in mapped.values() for source in value.get("sources", [])
        if top_raw and source["raw_label"] == top_raw["label"]
    ]
    out_of_taxonomy = bool(
        top_raw and top_raw["score"] >= 0.25
        and (not top_mappings or all(value["mapping_type"] != "direct" for value in top_mappings))
    )
    return {
        "status": "ready",
        "engine": route.get("engine"),
        "model": {
            "name": (route.get("result") or {}).get("model_name"),
            "version": (route.get("result") or {}).get("model_version"),
            "aggregation": (route.get("result") or {}).get("aggregation"),
        },
        "raw_labels": normalized_labels[:10],
        "mapped_styles": mapped,
        "unmapped_labels": unmapped[:10],
        "ignored_low_score_labels": ignored_low_score[:10],
        "route_support_floor": MODEL_ROUTE_SUPPORT_FLOOR,
        "component_support_floor": MODEL_LABEL_COMPONENT_FLOOR,
        "route_support_enabled": route_support_enabled,
        "out_of_taxonomy": out_of_taxonomy,
    }


def _fuse_model_support(styles: list[dict[str, Any]], mapping: dict[str, Any]) -> None:
    mapped = mapping.get("mapped_styles") or {}
    for style in styles:
        style["native_score"] = style["score"]
        support = mapped.get(style["style_id"])
        if not support:
            style["model_support"] = None
            style["model_adjustment"] = 0.0
            continue
        mapping_quality = 1.0 if support["mapping_type"] == "direct" else 0.60
        adjustment = 0.18 * float(support["support"])
        style["score"] = round(_clamp(style["score"] + adjustment), 4)
        style["reliability"] = round(_clamp(
            style["reliability"] + 0.12 * float(support["support"]) * mapping_quality
        ), 4)
        style["confidence"] = round(min(style["score"], style["reliability"]), 4)
        style["detected"] = bool(
            style["score"] >= 0.55 and style["reliability"] >= 0.45
            and style["required_evidence_ratio"] >= 1.0
            and style["evidence_count"] >= style["minimum_evidence"]
        )
        style["model_support"] = support
        style["model_adjustment"] = round(adjustment, 4)


def _instrument_label_evidence(features: dict[str, Any]) -> dict[str, Any]:
    route = (((features.get("model_evidence") or {}).get("routes") or {}).get("instrument_tags") or {})
    if route.get("status") != "ready":
        return {"status": "unavailable", "engine": route.get("engine"), "raw_labels": []}
    labels = []
    for item in ((route.get("result") or {}).get("labels") or [])[:20]:
        if not isinstance(item, dict) or not item.get("label"):
            continue
        labels.append({
            "label": str(item["label"]),
            "score": round(_clamp(item.get("score", 0.0) or 0.0), 4),
        })
    return {
        "status": "ready",
        "engine": route.get("engine"),
        "license": route.get("license"),
        "raw_labels": labels,
        "use": "auxiliary_observation_only",
    }


def _boundary_profile(groups: dict, weights: dict[str, float]) -> tuple[float, float, list[dict[str, Any]]]:
    available = total = weighted = 0.0
    evidence = []
    for path, weight in weights.items():
        total += weight
        feature = _feature(groups, path)
        if not _available(feature):
            continue
        score, reliability, effective = _effective(feature)
        available += weight
        weighted += weight * effective
        evidence.append({
            "feature": path,
            "score": round(score, 4),
            "reliability": round(reliability, 4),
            "effective_score": round(effective, 4),
        })
    return weighted / max(available, 1e-8), available / max(total, 1e-8), evidence


def _resolve_dance_boundaries(styles: list[dict[str, Any]], groups: dict) -> dict[str, Any]:
    by_id = {item["style_id"]: item for item in styles}
    adjustments = {style_id: 0.0 for style_id in {value for pair in BOUNDARY_PROFILES for value in pair}}
    comparisons = []
    for (left_id, right_id), (left_profile, right_profile) in BOUNDARY_PROFILES.items():
        left = by_id[left_id]
        right = by_id[right_id]
        score_gap = abs(float(left["score"]) - float(right["score"]))
        left_score, left_coverage, left_evidence = _boundary_profile(groups, left_profile)
        right_score, right_coverage, right_evidence = _boundary_profile(groups, right_profile)
        applied = score_gap <= BOUNDARY_PAIR_MAX_GAP and min(left_coverage, right_coverage) >= 0.50
        signed_adjustment = _clamp(abs(left_score - right_score)) * 0.05
        if left_score < right_score:
            signed_adjustment *= -1.0
        if applied:
            adjustments[left_id] += signed_adjustment
            adjustments[right_id] -= signed_adjustment
        comparisons.append({
            "pair": [left_id, right_id],
            "pre_boundary_gap": round(score_gap, 4),
            "applied": applied,
            "left_profile_score": round(left_score, 4),
            "right_profile_score": round(right_score, 4),
            "left_coverage": round(left_coverage, 4),
            "right_coverage": round(right_coverage, 4),
            "signed_adjustment_to_left": round(signed_adjustment if applied else 0.0, 4),
            "left_evidence": left_evidence,
            "right_evidence": right_evidence,
        })
    applied_by_style = {}
    for style_id, raw_adjustment in adjustments.items():
        style = by_id[style_id]
        adjustment = float(np.clip(
            raw_adjustment, -BOUNDARY_TOTAL_ADJUSTMENT_CAP, BOUNDARY_TOTAL_ADJUSTMENT_CAP,
        ))
        style["pre_boundary_score"] = style["score"]
        style["boundary_adjustment"] = round(adjustment, 4)
        style["score"] = round(_clamp(float(style["score"]) + adjustment), 4)
        style["confidence"] = round(min(style["score"], style["reliability"]), 4)
        style["detected"] = bool(
            style["score"] >= 0.55 and style["reliability"] >= 0.45
            and style["required_evidence_ratio"] >= 1.0
            and style["evidence_count"] >= style["minimum_evidence"]
        )
        applied_by_style[style_id] = round(adjustment, 4)
    return {
        "version": "funk_disco_house_pairwise_v1",
        "maximum_pair_gap": BOUNDARY_PAIR_MAX_GAP,
        "maximum_total_adjustment": BOUNDARY_TOTAL_ADJUSTMENT_CAP,
        "comparisons": comparisons,
        "adjustments": applied_by_style,
        "rule": "close candidates only; native required evidence remains mandatory",
    }


def empty_style_analysis(reason: str = "pre_style_features_unavailable") -> dict[str, Any]:
    return {
        "version": STYLE_ANALYSIS_VERSION,
        "taxonomy_version": STYLE_TAXONOMY_VERSION,
        "status": "unavailable",
        "needs_review": True,
        "review_reasons": [reason],
        "top_styles": [],
        "primary_style": None,
        "primary_style_candidate": None,
        "detected_styles": [],
        "style_influences": [],
        "styles": [],
        "group_scores": {},
        "model_label_evidence": {
            "status": "unavailable", "raw_labels": [], "mapped_styles": {},
            "unmapped_labels": [], "ignored_low_score_labels": [],
            "out_of_taxonomy": False,
        },
        "instrument_label_evidence": {"status": "unavailable", "raw_labels": []},
        "external_tags": {"styles": [], "instruments": []},
        "boundary_resolution": {"version": "funk_disco_house_pairwise_v1", "comparisons": []},
        "out_of_taxonomy": False,
        "confidence": 0.0,
        "reliability": 0.0,
    }


def classify_high_frequency_styles(features: dict[str, Any] | None) -> dict[str, Any]:
    """Score every style in parallel and return absolute, explainable scores."""
    features = features or {}
    groups = features.get("feature_groups")
    if not isinstance(groups, dict) or not groups:
        return empty_style_analysis()
    bpm = ((features.get("music_context") or {}).get("bpm"))
    styles = [
        _score_style(style_id, rule, groups, bpm)
        for style_id, rule in STYLE_DEFINITIONS.items()
    ]
    model_mapping = _model_label_mapping(features)
    _fuse_model_support(styles, model_mapping)
    boundary_resolution = _resolve_dance_boundaries(styles, groups)
    styles.sort(key=lambda item: item["score"], reverse=True)
    for rank, item in enumerate(styles, 1):
        item["rank"] = rank
    top = styles[:3]
    all_detected_styles = [item for item in styles if item["detected"]]
    detected_styles = all_detected_styles[:3]
    primary_style = detected_styles[0] if detected_styles else None
    style_influences = [
        item for item in styles
        if not item["detected"]
        and item["score"] >= 0.48
        and item["reliability"] >= 0.40
        and item["required_evidence_ratio"] >= 0.50
        and item["evidence_count"] >= max(1, item["minimum_evidence"] - 1)
    ][:3]
    instrument_mapping = _instrument_label_evidence(features)
    top_score = top[0]["score"] if top else 0.0
    margin = top_score - top[1]["score"] if len(top) >= 2 else top_score
    review_reasons = []
    if features.get("status") != "ready":
        review_reasons.append("feature_analysis_degraded")
    if top_score < 0.55:
        review_reasons.append("no_style_above_detection_threshold")
    if primary_style is None:
        review_reasons.append("no_style_met_complete_detection_conditions")
    elif top and top[0]["style_id"] != primary_style["style_id"]:
        review_reasons.append("highest_candidate_not_fully_detected")
    if margin < 0.07:
        review_reasons.append("top_styles_too_close")
    if top and top[0]["feature_coverage"] < 0.60:
        review_reasons.append("top_style_low_feature_coverage")
    if top and top[0]["required_evidence_ratio"] < 1.0:
        review_reasons.append("top_style_missing_required_evidence")
    if top and top[0]["confidence"] < 0.58:
        review_reasons.append("top_style_low_confidence")
    if top and top[0]["reliability"] < 0.62:
        review_reasons.append("top_style_low_evidence_reliability")
    if model_mapping["out_of_taxonomy"]:
        review_reasons.append("top_model_label_outside_or_adjacent_to_21_style_taxonomy")

    group_scores = {}
    for group, style_ids in STYLE_GROUPS.items():
        candidates = [item for item in styles if item["style_id"] in style_ids]
        best = candidates[0] if candidates else None
        group_scores[group] = {
            "score": best["score"] if best else 0.0,
            "best_style": best["style_id"] if best else None,
            "detected_style_count": sum(item["detected"] for item in candidates),
        }
    decision_style = primary_style or (top[0] if top else None)
    confidence = _clamp(
        (decision_style["confidence"] if decision_style else 0.0)
        * (0.62 + 0.38 * _clamp(margin / 0.18))
    )
    return {
        "version": STYLE_ANALYSIS_VERSION,
        "taxonomy_version": STYLE_TAXONOMY_VERSION,
        "status": "ready" if not review_reasons else "needs_review",
        "needs_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "top_styles": top,
        "primary_style": primary_style,
        "primary_style_candidate": top[0] if top else None,
        "detected_styles": detected_styles,
        "detected_style_count": len(all_detected_styles),
        "style_influences": style_influences,
        "styles": styles,
        "group_scores": group_scores,
        "model_label_evidence": model_mapping,
        "instrument_label_evidence": instrument_mapping,
        "external_tags": {
            "styles": model_mapping.get("raw_labels", []),
            "instruments": instrument_mapping.get("raw_labels", []),
        },
        "boundary_resolution": boundary_resolution,
        "out_of_taxonomy": model_mapping["out_of_taxonomy"],
        "confidence": round(confidence, 4),
        "reliability": decision_style["reliability"] if decision_style else 0.0,
        "decision": {
            "detection_threshold": 0.55,
            "review_margin_threshold": 0.07,
            "top_score": top_score,
            "top_two_margin": round(margin, 4),
            "normalization": "absolute_scores_not_forced_to_sum_to_one",
            "model_fusion": "optional_positive_support_capped_at_0.18; native requirements remain mandatory",
            "primary_style_semantics": "highest-scoring fully detected style; null when no style satisfies all gates",
            "multi_label_semantics": "up to three independently detected styles; not a forced top-k",
            "influence_semantics": "near-threshold partial evidence, separate from detected styles",
        },
    }
