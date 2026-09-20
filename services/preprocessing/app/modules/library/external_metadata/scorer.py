"""External tag scoring and final style-score fusion."""
from __future__ import annotations

from collections.abc import Mapping

from app.modules.dj_control.style_taxonomy import STYLE_TAG_PROFILE
from app.modules.library.external_metadata.normalizer import normalize_labels


def clamp01(value: float | int | None, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return default


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    cleaned = {k: max(0.0, float(v or 0.0)) for k, v in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        return {k: 0.0 for k in cleaned}
    return {k: v / total for k, v in cleaned.items()}


def score_external_tags_for_style(
    normalized_tags: list[str],
    style: str,
    source_confidence: float = 1.0,
) -> float:
    profile = STYLE_TAG_PROFILE.get(style)
    if not profile:
        return 0.0
    tags = normalize_labels(normalized_tags)
    if not tags:
        return 0.0

    strong = set(profile.get("strong", []))
    medium = set(profile.get("medium", []))
    negative = set(profile.get("negative", []))
    score = 0.20
    matched = 0
    for tag in set(tags):
        if tag in strong:
            score += 0.30
            matched += 1
        elif tag in medium:
            score += 0.15
            matched += 1
        elif tag in negative:
            score -= 0.25
    if matched:
        score += min(0.15, matched * 0.03)
    score *= 0.55 + 0.45 * clamp01(source_confidence, 1.0)
    return round(clamp01(score), 4)


def fuse_external_source_scores(
    source_scores: Mapping[str, float | None],
    source_weights: Mapping[str, float],
) -> float | None:
    weighted = 0.0
    total = 0.0
    for source, weight in source_weights.items():
        value = source_scores.get(source)
        if value is None:
            continue
        weighted += clamp01(value) * max(0.0, float(weight or 0.0))
        total += max(0.0, float(weight or 0.0))
    if total <= 0:
        return None
    return round(clamp01(weighted / total), 4)


def fuse_final_style_score(
    *,
    external_platform_score: float | None,
    local_fingerprint_score: float | None,
    manual_style_score: float | None,
    tunable_adjustment_score: float | None,
    weights: Mapping[str, float],
) -> float:
    components = {
        "external": external_platform_score,
        "local": local_fingerprint_score,
        "manual": manual_style_score,
        "tunable": tunable_adjustment_score,
    }
    weighted = 0.0
    total = 0.0
    for key, value in components.items():
        if value is None:
            continue
        weight = max(0.0, float(weights.get(key, 0.0) or 0.0))
        weighted += clamp01(value) * weight
        total += weight
    if total <= 0:
        return 0.0
    return round(clamp01(weighted / total), 4)

