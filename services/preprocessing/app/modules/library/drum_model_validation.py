"""Resolve versioned held-out validation for optional drum workers."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


DRUM_MODEL_VALIDATION_VERSION = "drum_model_validation_v1"
DEFAULT_PATH = Path(__file__).parents[3] / "config" / "model_validation" / "drum_transcription_v1.json"


@lru_cache(maxsize=2)
def load_drum_model_validations(path: str | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_PATH
    if not target.is_file():
        return {"version": DRUM_MODEL_VALIDATION_VERSION, "models": []}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("version") != DRUM_MODEL_VALIDATION_VERSION:
        raise ValueError(f"unsupported drum validation version: {payload.get('version')}")
    return payload


def resolve_drum_model_validation(
    model_route: dict[str, Any] | None,
    *,
    validations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = (model_route or {}).get("result") or {}
    engine = str(payload.get("engine") or (model_route or {}).get("engine") or "")
    version = str(payload.get("model_version") or "")
    thresholds = payload.get("thresholds") or {}
    for entry in (validations or load_drum_model_validations()).get("models", []):
        if entry.get("engine") != engine or str(entry.get("model_version")) != version:
            continue
        expected = entry.get("thresholds") or {}
        if set(expected) != set(thresholds):
            continue
        if any(abs(float(expected[key]) - float(thresholds[key])) > 1e-9 for key in expected):
            continue
        return {
            "status": "matched",
            "version": DRUM_MODEL_VALIDATION_VERSION,
            **entry,
        }
    return {
        "status": "unvalidated",
        "version": DRUM_MODEL_VALIDATION_VERSION,
        "engine": engine or None,
        "model_version": version or None,
        "classes": {},
    }


def class_is_validated(validation: dict[str, Any] | None, name: str) -> bool:
    return bool((((validation or {}).get("classes") or {}).get(name) or {}).get("validated"))
