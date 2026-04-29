from __future__ import annotations

from math import exp
from typing import Any

import numpy as np

from app.modules.library.dance_style_rules import (
    DANCE_STYLES,
    FEATURE_WEIGHTS,
    GENRE_AUDIO_FEATURE_HINTS,
    MUSIC_FEATURES,
    STYLE_BPM_RANGES,
    STYLE_FEATURE_PROFILES,
)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _score_bpm_for_style(bpm: float | None, style: str) -> tuple[float, str | None]:
    if not bpm or bpm <= 0:
        return 0.5, None
    low, high = STYLE_BPM_RANGES.get(style, (60, 160))
    center = (low + high) / 2
    half_width = max((high - low) / 2, 1)
    distance = abs(bpm - center)
    if low <= bpm <= high:
        score = 1.0 - 0.18 * (distance / half_width)
        return _clamp(score, 0.76, 1.0), f"BPM {bpm:.1f} 在 {low}-{high} 的适跳区间"
    outside = min(abs(bpm - low), abs(bpm - high))
    score = exp(-outside / 18.0) * 0.72
    return _clamp(score, 0.0, 0.72), None


def _similarity(value: float | None, target: float) -> float:
    if value is None:
        return 0.5
    return _clamp(1.0 - abs(_clamp(float(value)) - target))


def _normalize_genre_name(name: str) -> str:
    normalized = name.lower().strip()
    normalized = normalized.replace("_", " ").replace("/", " ").replace("---", " ")
    normalized = normalized.replace("&", "&")
    return " ".join(normalized.split())


def _genre_matches(rule_name: str, genre_name: str) -> bool:
    rule = _normalize_genre_name(rule_name)
    genre = _normalize_genre_name(genre_name)
    if not rule or not genre:
        return False
    return rule == genre or rule in genre or genre in rule


def _derive_feature_hints_from_genres(genres: list[dict[str, Any]]) -> tuple[dict[str, float], list[str]]:
    weighted: dict[str, float] = {}
    weights: dict[str, float] = {}
    matched_genres: list[str] = []

    for item in genres or []:
        name = _normalize_genre_name(str(item.get("name", "")))
        confidence = _clamp(float(item.get("confidence") or 0.0))
        if confidence <= 0:
            continue
        for key, hints in GENRE_AUDIO_FEATURE_HINTS.items():
            if _genre_matches(key, name):
                matched_genres.append(name)
                for feature, hint_value in hints.items():
                    weighted[feature] = weighted.get(feature, 0.0) + float(hint_value) * confidence
                    weights[feature] = weights.get(feature, 0.0) + confidence

    hints = {feature: weighted[feature] / weights[feature] for feature in weighted if weights.get(feature)}
    return hints, sorted(set(matched_genres))[:8]


def _estimate_beat_stability(beat_points: list[float] | None) -> float | None:
    if not beat_points or len(beat_points) < 6:
        return None
    intervals = np.diff(np.array(beat_points[: min(len(beat_points), 128)], dtype=float))
    median = float(np.median(intervals)) if len(intervals) else 0.0
    if median <= 0:
        return None
    return _clamp(1.0 - min(float(np.std(intervals) / median), 1.0))


def _derive_phrase_features(phrase_map: list[dict[str, Any]] | None) -> dict[str, float]:
    if not phrase_map:
        return {}
    labels = [str(item.get("label", "")).lower() for item in phrase_map]
    label_set = set(labels)
    phrase_count = len(labels)
    result: dict[str, float] = {}

    if phrase_count >= 5:
        result["choreo"] = 0.74
        result["flow"] = 0.68
    if {"drop", "buildup", "breakdown"} & label_set:
        result["power"] = 0.76
        result["club_drive"] = 0.70
    if labels.count("breakdown") or labels.count("break"):
        result["technical"] = 0.64
    return result


def _merge_feature_values(*sources: tuple[dict[str, float | None], float]) -> dict[str, float]:
    weighted: dict[str, float] = {}
    weights: dict[str, float] = {}
    for values, source_weight in sources:
        for feature, value in values.items():
            if feature not in MUSIC_FEATURES or value is None:
                continue
            weighted[feature] = weighted.get(feature, 0.0) + _clamp(float(value)) * source_weight
            weights[feature] = weights.get(feature, 0.0) + source_weight
    return {feature: round(weighted[feature] / weights[feature], 3) for feature in weighted if weights.get(feature)}


def derive_music_features(
    *,
    genres: list[dict[str, Any]] | None,
    bpm: float | None,
    energy: float | None,
    beat_confidence: float | None,
    beat_points: list[float] | None = None,
    phrase_map: list[dict[str, Any]] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = params or {}
    genre_hints, matched_genres = _derive_feature_hints_from_genres(genres or [])
    beat_stability = _estimate_beat_stability(beat_points)
    phrase_features = _derive_phrase_features(phrase_map)

    measured = {
        "energy": energy,
        "beat_confidence": beat_confidence,
        "groove": beat_stability if beat_stability is not None else beat_confidence,
        "percussive_density": beat_confidence,
        "club_drive": energy,
        "power": energy,
    }

    features = _merge_feature_values(
        (genre_hints, 0.42),
        (measured, 0.43),
        (phrase_features, 0.15),
    )

    for feature in MUSIC_FEATURES:
        features.setdefault(feature, 0.5)

    if bpm:
        if 115 <= bpm <= 132:
            features["club_drive"] = round(_clamp(features["club_drive"] * 0.75 + 0.25), 3)
        if 82 <= bpm <= 112:
            features["bounce"] = round(_clamp(features["bounce"] * 0.75 + 0.25), 3)
        if bpm >= 128:
            features["percussive_density"] = round(_clamp(features["percussive_density"] * 0.75 + 0.25), 3)

    preference_keys = {
        "power": "prefer_power",
        "groove": "prefer_groove",
        "choreo": "prefer_choreo",
        "technical": "prefer_technical",
        "flow": "prefer_flow",
        "bounce": "prefer_bounce",
        "club_drive": "prefer_club",
    }
    for feature, param_key in preference_keys.items():
        if param_key in params:
            features[feature] = round(_clamp(features[feature] * 0.7 + _clamp(float(params[param_key])) * 0.3), 3)

    top_features = sorted(features.items(), key=lambda item: item[1], reverse=True)[:6]
    return {
        "features": features,
        "matched_genres": matched_genres,
        "beat_stability": None if beat_stability is None else round(beat_stability, 3),
        "top_features": [{"name": name, "value": value} for name, value in top_features],
        "source": "genre_hints+audio_params+phrase_v2",
    }


def _energy_class(energy: float | None) -> str:
    if energy is None:
        return "能量未知"
    if energy >= 0.75:
        return "高能量"
    if energy >= 0.45:
        return "中等能量"
    return "低能量"


def _reason_for_feature(feature: str, value: float, style: str) -> str:
    labels = {
        "energy": "能量",
        "beat_confidence": "节拍清晰度",
        "groove": "律动感",
        "power": "力量感",
        "choreo": "编舞适配",
        "technical": "技术动作适配",
        "bounce": "弹跳感",
        "flow": "流动性",
        "club_drive": "俱乐部驱动",
        "percussive_density": "打击密度",
        "syncopation": "切分律动",
        "smoothness": "顺滑度",
    }
    return f"{labels.get(feature, feature)} {value:.2f} 贴合 {style}"


def classify_dance_styles(
    *,
    genres: list[dict[str, Any]] | None,
    bpm: float | None,
    energy: float | None,
    beat_confidence: float | None,
    beat_points: list[float] | None = None,
    phrase_map: list[dict[str, Any]] | None = None,
    params: dict[str, Any] | None = None,
    top_k: int = 5,
    threshold: float = 0.35,
) -> dict[str, Any]:
    params = params or {}
    music_features = derive_music_features(
        genres=genres,
        bpm=bpm,
        energy=energy,
        beat_confidence=beat_confidence,
        beat_points=beat_points,
        phrase_map=phrase_map,
        params=params,
    )
    feature_values = music_features["features"]

    allow_styles = set(params.get("allow_styles") or DANCE_STYLES)
    block_styles = set(params.get("block_styles") or [])

    results: list[dict[str, Any]] = []
    for style in DANCE_STYLES:
        if style not in allow_styles or style in block_styles:
            continue
        profile = STYLE_FEATURE_PROFILES[style]
        bpm_score, bpm_reason = _score_bpm_for_style(bpm, style)
        score = bpm_score * FEATURE_WEIGHTS["bpm"]
        feature_scores: dict[str, float] = {"bpm": round(bpm_score, 3)}
        reasons = []
        if bpm_reason:
            reasons.append(bpm_reason)

        ranked_matches: list[tuple[str, float, float]] = []
        for feature, weight in FEATURE_WEIGHTS.items():
            if feature == "bpm":
                continue
            value = feature_values.get(feature)
            feature_score = _similarity(value, float(profile[feature]))
            feature_scores[feature] = round(feature_score, 3)
            score += feature_score * weight
            if value is not None:
                ranked_matches.append((feature, feature_score, float(value)))

        ranked_matches.sort(key=lambda item: item[1], reverse=True)
        for feature, feature_score, value in ranked_matches[:4]:
            if feature_score >= 0.78:
                reasons.append(_reason_for_feature(feature, value, style))

        genre_confidence = max([float(g.get("confidence") or 0.0) for g in genres or []], default=0.0)
        confidence = _clamp(score * 0.76 + genre_confidence * 0.12 + (beat_confidence or 0.5) * 0.12)
        if score >= threshold:
            if not reasons:
                reasons.append(f"整体音乐特征与 {_energy_class(energy)} 曲目适配")
            results.append({
                "style": style,
                "score": round(float(score), 3),
                "confidence": round(float(confidence), 3),
                "reasons": reasons[:5],
                "feature_scores": feature_scores,
                "source": "feature_scoring_v2",
            })

    results.sort(key=lambda item: item["score"], reverse=True)
    return {
        "dance_styles": results[:top_k],
        "dance_style_scores": {item["style"]: item["score"] for item in results[:top_k]},
        "music_features": music_features,
        "classifier_version": "feature_scoring_v2",
    }
