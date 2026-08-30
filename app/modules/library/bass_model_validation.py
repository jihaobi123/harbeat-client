"""Resolve versioned held-out validation for the optional bass note worker."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


BASS_MODEL_VALIDATION_VERSION = "bass_model_validation_v1"
DEFAULT_PATH = Path(__file__).parents[3] / "config" / "model_validation" / "bass_transcription_v1.json"


@lru_cache(maxsize=2)
def load_bass_model_validations(path: str | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_PATH
    if not target.is_file():
        return {"version": BASS_MODEL_VALIDATION_VERSION, "models": []}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("version") != BASS_MODEL_VALIDATION_VERSION:
        raise ValueError(f"unsupported bass validation version: {payload.get('version')}")
    return payload


def resolve_bass_model_validation(
    model_route: dict[str, Any] | None,
    *,
    validations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = (model_route or {}).get("result") or {}
    engine = str(payload.get("engine") or (model_route or {}).get("engine") or "")
    version = str(payload.get("model_version") or "")
    model_name = str(payload.get("model_name") or "")
    for entry in (validations or load_bass_model_validations()).get("models", []):
        if (
            entry.get("engine") == engine
            and str(entry.get("model_version")) == version
            and str(entry.get("model_name")) == model_name
        ):
            return {"status": "matched", "version": BASS_MODEL_VALIDATION_VERSION, **entry}
    return {
        "status": "unvalidated",
        "version": BASS_MODEL_VALIDATION_VERSION,
        "engine": engine or None,
        "model_version": version or None,
        "model_name": model_name or None,
        "capabilities": {},
    }


def capability_is_validated(validation: dict[str, Any] | None, name: str) -> bool:
    return bool((((validation or {}).get("capabilities") or {}).get(name) or {}).get("validated"))
