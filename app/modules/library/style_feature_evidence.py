"""Versioned evidence records shared by feature and style analysis.

The v3 contract makes a distinction that the legacy payload could not express:
an analyser may have run and found no feature, or it may not have had the audio
source required to make a decision.  Style scoring must never treat the latter
as negative evidence.
"""
from __future__ import annotations

from typing import Any, Literal

import numpy as np


STYLE_FEATURE_EVIDENCE_VERSION = "pre_style_evidence_v3"
Availability = Literal["available", "unavailable"]
EvidenceLevel = Literal["confirmed", "probable", "candidate", "unavailable"]


def _clamp(value: float) -> float:
    return float(np.clip(float(value), 0.0, 1.0))


def evidence_level(
    score: float,
    confidence: float,
    *,
    detected: bool,
) -> EvidenceLevel:
    """Return an evidence strength without turning absence into a genre claim."""
    if detected and score >= 0.78 and confidence >= 0.72:
        return "confirmed"
    if detected and score >= 0.62 and confidence >= 0.52:
        return "probable"
    return "candidate"


def make_feature_evidence(
    score: float,
    *,
    threshold: float = 0.55,
    confidence: float = 1.0,
    evidence: dict[str, Any] | None = None,
    time_ranges: list[dict[str, Any]] | None = None,
    sources: list[str] | None = None,
    analysis_method: str,
) -> dict[str, Any]:
    """Build an available feature decision using the v3 evidence contract."""
    normalized_score = _clamp(score)
    normalized_confidence = _clamp(confidence)
    detected = normalized_score >= threshold
    return {
        "availability": "available",
        "detected": detected,
        "score": round(normalized_score, 4),
        "decision_threshold": round(_clamp(threshold), 4),
        "confidence": round(normalized_confidence, 4),
        "evidence_level": evidence_level(
            normalized_score,
            normalized_confidence,
            detected=detected,
        ),
        "analysis_method": analysis_method,
        "sources": list(dict.fromkeys(sources or [])),
        "time_ranges": list(time_ranges or []),
        "evidence": dict(evidence or {}),
    }


def unavailable_feature(
    reason: str,
    *,
    sources: list[str] | None = None,
    analysis_method: str,
) -> dict[str, Any]:
    """Build an explicit unknown value; ``detected=False`` would be incorrect."""
    return {
        "availability": "unavailable",
        "detected": None,
        "score": None,
        "decision_threshold": None,
        "confidence": 0.0,
        "evidence_level": "unavailable",
        "analysis_method": analysis_method,
        "sources": list(dict.fromkeys(sources or [])),
        "time_ranges": [],
        "evidence": {"reason": reason},
    }


def from_v2_feature(
    feature: dict[str, Any] | None,
    *,
    sources: list[str],
    analysis_method: str,
) -> dict[str, Any]:
    """Upgrade one legacy feature while preserving its measured evidence."""
    feature = feature or {}
    confidence = _clamp(feature.get("confidence", 0.0) or 0.0)
    if confidence <= 0.0 and not feature.get("evidence"):
        return unavailable_feature(
            "legacy_analyser_had_no_usable_input",
            sources=sources,
            analysis_method=analysis_method,
        )
    score = _clamp(feature.get("score", 0.0) or 0.0)
    threshold = _clamp(feature.get("decision_threshold", 0.55) or 0.55)
    upgraded = make_feature_evidence(
        score,
        threshold=threshold,
        confidence=confidence,
        evidence=feature.get("evidence") or {},
        time_ranges=feature.get("time_ranges") or [],
        sources=sources,
        analysis_method=analysis_method,
    )
    # Preserve a legacy decision at an exact historical boundary.
    upgraded["detected"] = bool(feature.get("detected", upgraded["detected"]))
    upgraded["evidence_level"] = evidence_level(
        score,
        confidence,
        detected=upgraded["detected"],
    )
    return upgraded


def to_v2_feature(feature: dict[str, Any]) -> dict[str, Any]:
    """Downgrade for old consumers; unavailability is retained in evidence."""
    if feature.get("availability") != "available":
        return {
            "detected": False,
            "score": 0.0,
            "decision_threshold": 0.55,
            "confidence": 0.0,
            "time_ranges": [],
            "evidence": {
                **dict(feature.get("evidence") or {}),
                "availability": "unavailable",
            },
        }
    return {
        "detected": bool(feature.get("detected")),
        "score": round(_clamp(feature.get("score", 0.0)), 4),
        "decision_threshold": round(_clamp(feature.get("decision_threshold", 0.55)), 4),
        "confidence": round(_clamp(feature.get("confidence", 0.0)), 4),
        "time_ranges": list(feature.get("time_ranges") or []),
        "evidence": dict(feature.get("evidence") or {}),
    }
