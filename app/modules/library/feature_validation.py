"""Minimize human review for pre-style audio feature validation.

The validator never treats model-generated labels as human ground truth.  It
automatically accepts only low-risk, high-confidence evidence and sends model
conflicts, threshold-borderline decisions, and semantic high-risk classes to a
small review queue.  A deterministic audit sample guards against systematic
errors without asking a reviewer to inspect every positive.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable


VALIDATION_VERSION = "pre_style_validation_v2"

HIGH_RISK_SEMANTIC = {
    "sub_808",
    "sliding_808",
    "log_drum",
    "wide_clap",
    "short_rim_snap",
    "short_metallic",
    "sustained_metallic",
    "low_pitched_drum",
    "mid_pitched_drum",
    "hand_drum_family",
    "tonal_percussion",
    "rage_synth",
}
EVENT_FEATURES = HIGH_RISK_SEMANTIC | {
    "bass_slide", "full_snare", "continuous_high_percussion", "repeated_tonal_motif",
    "jersey_club", "tamborzao", "drill_hat", "breakbeat", "afro_syncopation",
}
DETERMINISTIC_RHYTHM = {
    "four_on_floor",
    "backbeat_2_4",
    "halftime_snare_3",
    "tresillo",
    "dembow",
    "two_step",
    "swing",
    "jersey_club",
    "tamborzao",
    "drill_hat",
    "breakbeat",
    "afro_syncopation",
}


@dataclass(frozen=True)
class ReviewPolicy:
    minimum_auto_confidence: float = 0.76
    high_risk_auto_confidence: float = 0.88
    threshold_margin: float = 0.10
    audit_percent: float = 0.05
    max_items: int = 24
    max_items_per_track: int = 3
    max_items_per_feature: int = 2
    max_items_per_track_feature: int = 1
    clip_duration_seconds: float = 6.0


def _stable_fraction(value: str) -> float:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _source_type(feature: dict[str, Any]) -> str:
    evidence = feature.get("evidence") or {}
    return str(
        evidence.get("source_type")
        or feature.get("analysis_method")
        or evidence.get("detector")
        or "unknown"
    )


def _is_mature_source(source: str) -> bool:
    return source.startswith("mature_") or source == "mature_model"


def _representative_ranges(
    feature: dict[str, Any],
    *,
    duration: float,
    clip_duration: float,
    limit: int,
) -> list[dict[str, float]]:
    raw = feature.get("time_ranges") or []
    candidates: list[tuple[float, float]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            start = max(0.0, float(item.get("start", 0.0)))
            end = max(start, float(item.get("end", start)))
        except (TypeError, ValueError):
            continue
        center = (start + end) / 2.0
        candidates.append((center, max(end - start, 0.1)))
    if not candidates:
        anchors = [duration * 0.35]
    elif len(candidates) == 1 or limit == 1:
        anchors = [candidates[0][0]]
    else:
        anchors = [candidates[0][0], candidates[len(candidates) // 2][0], candidates[-1][0]][:limit]
    result = []
    seen = set()
    for center in anchors:
        start = max(0.0, min(max(0.0, duration - clip_duration), center - clip_duration / 2.0))
        end = min(duration, start + clip_duration)
        key = round(start, 1)
        if key in seen:
            continue
        seen.add(key)
        result.append({"start": round(start, 3), "end": round(end, 3)})
    return result


def _review_options(feature_name: str) -> list[str]:
    if feature_name in {"sub_bass", "sub_808", "bass_slide", "sliding_808", "log_drum"}:
        return ["sub_bass", "808", "sliding_808", "log_drum", "other_bass", "absent", "uncertain"]
    if feature_name in HIGH_RISK_SEMANTIC or feature_name in {"closed_hihat", "general_percussion"}:
        return [feature_name, "other_percussion", "absent", "uncertain"]
    return ["present", "absent", "uncertain"]


def _decision(
    track_id: str,
    group_name: str,
    feature_name: str,
    feature: dict[str, Any],
    policy: ReviewPolicy,
) -> tuple[str, list[str], float]:
    score = float(feature.get("score", 0.0) or 0.0)
    threshold = float(feature.get("decision_threshold", 0.55) or 0.55)
    confidence = float(feature.get("confidence", 0.0) or 0.0)
    detected = bool(feature.get("detected"))
    source = _source_type(feature)
    evidence = feature.get("evidence") or {}
    reasons: list[str] = []
    priority = 0.0

    if abs(score - threshold) <= policy.threshold_margin:
        reasons.append("near_decision_threshold")
        priority += 0.34
    required_confidence = (
        policy.high_risk_auto_confidence if feature_name in HIGH_RISK_SEMANTIC
        else policy.minimum_auto_confidence
    )
    if detected and confidence < required_confidence:
        reasons.append("insufficient_confidence")
        priority += 0.28
    if feature_name in HIGH_RISK_SEMANTIC and detected and not _is_mature_source(source):
        reasons.append("semantic_class_uses_proxy")
        priority += 0.50
    if feature_name in EVENT_FEATURES and detected and not feature.get("time_ranges"):
        reasons.append("detected_without_auditable_time_range")
        priority += 0.25
    if feature_name == "sliding_808" and detected:
        identity = float(evidence.get("sub_808_identity_score", 0.0) or 0.0)
        motion = float(evidence.get("bass_slide_score", 0.0) or 0.0)
        if identity < 0.62 or motion < 0.55:
            reasons.append("sliding_808_components_inconsistent")
            priority += 0.55
    if feature_name in DETERMINISTIC_RHYTHM and detected:
        bars = int(evidence.get("bars_analyzed", 0) or 0)
        if bars < 8:
            reasons.append("insufficient_bar_coverage")
            priority += 0.30

    audit_key = f"{track_id}:{group_name}:{feature_name}"
    audit = detected and not reasons and _stable_fraction(audit_key) < policy.audit_percent
    if audit:
        reasons.append("deterministic_quality_audit")
        priority += 0.12

    if reasons:
        return "manual_review", reasons, min(1.0, priority + (0.12 if detected else 0.0))
    if detected:
        return "auto_accept", [], max(0.0, confidence)
    return "auto_negative", [], max(0.0, confidence)


def triage_track_features(
    *,
    track_id: str,
    title: str,
    duration: float,
    feature_analysis: dict[str, Any],
    policy: ReviewPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or ReviewPolicy()
    groups = feature_analysis.get("feature_groups") or {}
    auto_accept: list[dict[str, Any]] = []
    auto_negative: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for group_name, group_features in groups.items():
        for feature_name, feature in (group_features or {}).items():
            if not isinstance(feature, dict):
                continue
            if feature.get("availability") == "unavailable":
                unavailable.append({
                    "track_id": track_id,
                    "title": title,
                    "group": group_name,
                    "feature": feature_name,
                    "predicted": None,
                    "score": None,
                    "confidence": 0.0,
                    "source_type": _source_type(feature),
                    "evidence": feature.get("evidence") or {},
                    "disposition": "unavailable",
                })
                continue
            disposition, reasons, priority = _decision(
                track_id, group_name, feature_name, feature, policy,
            )
            base = {
                "track_id": track_id,
                "title": title,
                "group": group_name,
                "feature": feature_name,
                "predicted": feature.get("detected"),
                "score": float(feature.get("score", 0.0) or 0.0),
                "decision_threshold": float(feature.get("decision_threshold", 0.55) or 0.55),
                "confidence": float(feature.get("confidence", 0.0) or 0.0),
                "source_type": _source_type(feature),
                "evidence": feature.get("evidence") or {},
                "disposition": disposition,
            }
            if disposition == "manual_review":
                ranges = _representative_ranges(
                    feature,
                    duration=duration,
                    clip_duration=policy.clip_duration_seconds,
                    limit=2 if feature_name in HIGH_RISK_SEMANTIC else 1,
                )
                for index, time_range in enumerate(ranges):
                    review.append({
                        **base,
                        "review_id": f"{track_id}:{group_name}:{feature_name}:{index}",
                        "reasons": reasons,
                        "priority": round(priority, 4),
                        "time_range": time_range,
                        "options": _review_options(feature_name),
                    })
            elif disposition == "auto_accept":
                auto_accept.append(base)
            else:
                auto_negative.append(base)
    return {
        "track_id": track_id,
        "title": title,
        "duration": round(float(duration), 3),
        "auto_accept": auto_accept,
        "auto_negative": auto_negative,
        "unavailable": unavailable,
        "manual_review": review,
    }


def minimize_review_queue(
    track_results: Iterable[dict[str, Any]],
    *,
    policy: ReviewPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or ReviewPolicy()
    tracks = list(track_results)
    candidates = sorted(
        (item for track in tracks for item in track.get("manual_review", [])),
        key=lambda item: (-float(item.get("priority", 0.0)), item["review_id"]),
    )
    selected = []
    per_track: dict[str, int] = {}
    per_feature: dict[str, int] = {}
    per_track_feature: dict[tuple[str, str], int] = {}
    deferred = []
    for item in candidates:
        track_id = item["track_id"]
        feature_name = item["feature"]
        allowed = (
            len(selected) < policy.max_items
            and per_track.get(track_id, 0) < policy.max_items_per_track
            and per_feature.get(feature_name, 0) < policy.max_items_per_feature
            and per_track_feature.get((track_id, feature_name), 0)
            < policy.max_items_per_track_feature
        )
        if not allowed:
            deferred.append(item)
            continue
        selected.append(item)
        per_track[track_id] = per_track.get(track_id, 0) + 1
        per_feature[feature_name] = per_feature.get(feature_name, 0) + 1
        key = (track_id, feature_name)
        per_track_feature[key] = per_track_feature.get(key, 0) + 1
    return {
        "version": VALIDATION_VERSION,
        "policy": policy.__dict__,
        "summary": {
            "track_count": len(tracks),
            "auto_accept_count": sum(len(track.get("auto_accept", [])) for track in tracks),
            "auto_negative_count": sum(len(track.get("auto_negative", [])) for track in tracks),
            "unavailable_count": sum(len(track.get("unavailable", [])) for track in tracks),
            "manual_candidate_count": len(candidates),
            "manual_selected_count": len(selected),
            "manual_deferred_count": len(deferred),
        },
        "review_items": selected,
        "deferred_items": deferred,
        "tracks": tracks,
    }
