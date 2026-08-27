"""Versioned evidence records shared by feature and style analysis."""
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
