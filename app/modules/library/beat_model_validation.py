"""Bind beat/downbeat accuracy claims to an exact model and postprocessor."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


BEAT_MODEL_VALIDATION_VERSION = "beat_model_validation_v1"
DEFAULT_PATH = Path(__file__).parents[3] / "config" / "model_validation" / "beat_tracking_v1.json"


@lru_cache(maxsize=2)
def load_beat_model_validations(path: str | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_PATH
    if not target.is_file():
        return {"version": BEAT_MODEL_VALIDATION_VERSION, "models": []}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("version") != BEAT_MODEL_VALIDATION_VERSION:
        raise ValueError(f"unsupported beat validation version: {payload.get('version')}")
    return payload


def resolve_beat_model_validation(
    route: dict[str, Any],
    *,
    validations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    engine = str(route.get("engine") or "")
    postprocessor = str(route.get("postprocessor") or "")
    for entry in (validations or load_beat_model_validations()).get("models", []):
        if entry.get("engine") != engine or entry.get("postprocessor") != postprocessor:
            continue
        threshold = float(entry["downbeats"]["confidence_gate"]["threshold"])
        confidence = float(route.get("downbeat_peak_probability_mean") or 0.0)
        downbeat_validated = bool(
            entry["downbeats"].get("validated") and confidence >= threshold
        )
        return {
            "status": "matched",
            "version": BEAT_MODEL_VALIDATION_VERSION,
            "engine": engine,
            "beat_validated": bool(entry["beats"].get("validated")),
            "downbeat_validated": downbeat_validated,
            "meter_validated": bool(entry.get("meter", {}).get("validated") and downbeat_validated),
            "downbeat_status": (
                "validated" if downbeat_validated else "abstained_low_confidence"
            ),
            "downbeat_confidence": round(confidence, 4),
            "downbeat_confidence_threshold": threshold,
            "benchmark": entry.get("benchmark"),
            "restrictions": entry.get("restrictions", []),
        }
    return {
        "status": "unvalidated",
        "version": BEAT_MODEL_VALIDATION_VERSION,
        "engine": engine or None,
        "beat_validated": False,
        "downbeat_validated": False,
        "meter_validated": False,
        "downbeat_status": "unvalidated",
    }
