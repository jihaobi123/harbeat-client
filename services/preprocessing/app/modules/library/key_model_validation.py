"""Resolve confidence-gated held-out validation for musical key estimates."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


KEY_MODEL_VALIDATION_VERSION = "key_model_validation_v1"
DEFAULT_PATH = Path(__file__).parents[3] / "config" / "model_validation" / "key_estimation_v1.json"


@lru_cache(maxsize=2)
def load_key_model_validations(path: str | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_PATH
    if not target.is_file():
        return {"version": KEY_MODEL_VALIDATION_VERSION, "models": []}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("version") != KEY_MODEL_VALIDATION_VERSION:
        raise ValueError(f"unsupported key validation version: {payload.get('version')}")
    return payload


def resolve_key_model_validation(
    route: dict[str, Any] | None,
    *,
    validations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route = route or {}
    engine = str(route.get("engine") or "")
    model_version = str(route.get("model_version") or "")
    worker_engine = str(route.get("worker_engine") or "")
    confidence = float(route.get("key_confidence") or 0.0)
    for entry in (validations or load_key_model_validations()).get("models", []):
        if (
            entry.get("engine") != engine
            or str(entry.get("model_version")) != model_version
            or entry.get("worker_engine") != worker_engine
        ):
            continue
        threshold = float(entry["confidence_gate"]["threshold"])
        validated = bool(entry.get("validated") and confidence >= threshold)
        return {
            "status": "matched",
            "version": KEY_MODEL_VALIDATION_VERSION,
            "engine": engine,
            "model_version": model_version,
            "validated": validated,
            "decision": "confirmed" if validated else "abstained_low_confidence",
            "model_confidence": round(confidence, 4),
            "confidence_threshold": threshold,
            "heldout_exact_accuracy": float(entry["heldout_exact_accuracy"]),
            "heldout_mirex_weighted_score": float(entry["heldout_mirex_weighted_score"]),
            "benchmark": entry.get("benchmark"),
            "restrictions": entry.get("restrictions", []),
        }
    return {
        "status": "unvalidated",
        "version": KEY_MODEL_VALIDATION_VERSION,
        "engine": engine or None,
        "model_version": model_version or None,
        "validated": False,
        "decision": "unvalidated",
        "model_confidence": round(confidence, 4),
    }
