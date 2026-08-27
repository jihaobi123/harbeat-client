"""Versioned evidence records shared by feature and style analysis."""
from __future__ import annotations

from typing import Any, Literal

import numpy as np


STYLE_FEATURE_EVIDENCE_VERSION = "pre_style_evidence_v4"
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
    measurement_confidence: float | None = None,
    source_quality: float = 1.0,
    estimator_quality: float = 1.0,
    calibration_status: str = "provisional",
    quality_flags: list[str] | None = None,
) -> dict[str, Any]:
    """Build an available feature decision using the v4 evidence contract.

    ``score`` describes acoustic match strength.  Reliability describes the
    quality of the measurement chain and deliberately stays independent of
    score so a confidently absent feature remains useful negative evidence.
    ``confidence`` is retained as a compatibility alias for reliability.
    """
    normalized_score = _clamp(score)
    measurement = _clamp(
        confidence if measurement_confidence is None else measurement_confidence
    )
    source = _clamp(source_quality)
    estimator = _clamp(estimator_quality)
    reliability = _clamp(0.45 * measurement + 0.30 * source + 0.25 * estimator)
    detected = normalized_score >= threshold
    return {
        "availability": "available",
        "detected": detected,
        "score": round(normalized_score, 4),
        "decision_threshold": round(_clamp(threshold), 4),
        "confidence": round(reliability, 4),
        "reliability": round(reliability, 4),
        "quality": {
            "measurement_confidence": round(measurement, 4),
            "source_quality": round(source, 4),
            "estimator_quality": round(estimator, 4),
            "calibration_status": calibration_status,
        },
        "quality_flags": list(dict.fromkeys(quality_flags or [])),
        "evidence_level": evidence_level(
            normalized_score,
            reliability,
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
        "reliability": 0.0,
        "quality": {
            "measurement_confidence": 0.0,
            "source_quality": 0.0,
            "estimator_quality": 0.0,
            "calibration_status": "unavailable",
        },
        "quality_flags": [reason],
        "evidence_level": "unavailable",
        "analysis_method": analysis_method,
        "sources": list(dict.fromkeys(sources or [])),
        "time_ranges": [],
        "evidence": {"reason": reason},
    }
