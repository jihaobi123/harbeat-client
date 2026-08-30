"""Versioned calibration policy for pre-style feature decisions."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from app.modules.library.feature_registry import definition_for


FEATURE_CALIBRATION_VERSION = "feature_calibration_v1"
DEFAULT_PATH = Path(__file__).parents[3] / "config" / "feature_calibration" / "v1.json"


@lru_cache(maxsize=4)
def load_feature_calibration(path: str | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_PATH
    if not target.is_file():
        return {"version": FEATURE_CALIBRATION_VERSION, "features": {}}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("version") != FEATURE_CALIBRATION_VERSION:
        raise ValueError(f"unsupported feature calibration version: {payload.get('version')}")
    return payload


def _interpolate(score: float, points: list[list[float]]) -> float:
    ordered = sorted((float(x), float(y)) for x, y in points)
    if not ordered:
        return float(score)
    x = np.asarray([item[0] for item in ordered], dtype=float)
    y = np.asarray([item[1] for item in ordered], dtype=float)
    return float(np.clip(np.interp(float(score), x, y), 0.0, 1.0))


def calibration_passes_release_gate(entry: dict[str, Any], *, group: str, name: str) -> bool:
    definition = definition_for(group, name)
    metrics = entry.get("held_out_metrics") or {}
    if entry.get("validation_mode") == "continuous":
        return bool(
            entry.get("status") == "validated"
            and int(metrics.get("sample_count", 0) or 0)
            >= int(entry.get("minimum_samples", 50))
            and float(metrics.get("within_tolerance_fraction", 0.0) or 0.0)
            >= float(entry.get("minimum_within_tolerance_fraction", 0.80))
        )
    return bool(
        entry.get("status") == "validated"
        and int(metrics.get("sample_count", 0) or 0) >= int(entry.get("minimum_samples", 50))
        and float(metrics.get("accuracy", 0.0) or 0.0) >= definition.minimum_accuracy
        and float(metrics.get("precision", 0.0) or 0.0) >= definition.minimum_precision
        and float(metrics.get("recall", 0.0) or 0.0) >= definition.minimum_recall
        and float(metrics.get("f1", 0.0) or 0.0) >= definition.minimum_f1
    )


def apply_feature_calibration(
    feature: dict[str, Any], *, group: str, name: str, calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Enrich legacy v4 evidence without pretending it has measured accuracy."""
    result = dict(feature)
    definition = definition_for(group, name)
    result["semantic_level"] = definition.semantic_level
    result["canonical_name"] = definition.canonical_name or name
    result["measurement_score"] = result.get("score")
    result["technical_reliability"] = float(result.get("reliability", 0.0) or 0.0)
    result["minimum_release_accuracy"] = definition.minimum_accuracy

    if result.get("availability") != "available":
        result.update({
            "probability": None,
            "decision": "unknown",
            "validation_status": "unavailable",
            "validation_scope": "unavailable",
            "calibration_version": FEATURE_CALIBRATION_VERSION,
            "style_required_allowed": False,
        })
        return result

    payload = calibration or load_feature_calibration()
    entry = ((payload.get("features") or {}).get(f"{group}.{name}") or {})
    allowed_methods = entry.get("analysis_methods") or []
    method_supported = (
        not allowed_methods
        or str(result.get("analysis_method") or "") in {str(value) for value in allowed_methods}
    )
    release_ready = (
        calibration_passes_release_gate(entry, group=group, name=name)
        and method_supported
    )
    status = (
        "validated" if release_ready
        else "failed_validation" if entry.get("status") == "failed_validation"
        else definition.default_status
    )
    score = float(result.get("score", 0.0) or 0.0)
    continuous_validation = entry.get("validation_mode") == "continuous"
    probability = (
        _interpolate(score, entry.get("probability_curve") or [])
        if release_ready and not continuous_validation else None
    )
    candidate_threshold = entry.get("candidate_threshold")
    confirmed_threshold = entry.get("confirmed_threshold")
    if status == "failed_validation":
        decision = "rejected"
    elif release_ready and continuous_validation:
        decision = "measured"
    elif release_ready and probability is not None:
        if confirmed_threshold is not None and probability >= float(confirmed_threshold):
            decision = "present"
        elif candidate_threshold is not None and probability >= float(candidate_threshold):
            decision = "candidate"
        else:
            decision = "absent"
    else:
        decision = "candidate" if bool(result.get("detected")) else "not_detected"
    result.update({
        "probability": None if probability is None else round(probability, 4),
        "decision": decision,
        "validation_status": status,
        "validation_scope": str(entry.get("validation_scope") or "unvalidated"),
        "candidate_threshold": candidate_threshold,
        "confirmed_threshold": confirmed_threshold,
        "calibration_version": str(payload.get("version") or FEATURE_CALIBRATION_VERSION),
        "calibration_metrics": dict(entry.get("held_out_metrics") or {}),
        "calibration_method_supported": method_supported,
        # Passing an acoustic/transcription benchmark is necessary but not
        # sufficient for a style hard-condition. Named musical semantics also
        # require an explicit, independently justified release decision.
        "style_required_allowed": bool(
            release_ready
            and definition.style_required_allowed
            and entry.get("style_required_allowed") is True
        ),
    })
    return result


def calibrate_feature_groups(groups: dict[str, Any]) -> dict[str, Any]:
    calibration = load_feature_calibration()
    return {
        group_name: {
            feature_name: apply_feature_calibration(
                feature, group=group_name, name=feature_name, calibration=calibration,
            ) if isinstance(feature, dict) else feature
            for feature_name, feature in (features or {}).items()
        }
        for group_name, features in groups.items()
    }
