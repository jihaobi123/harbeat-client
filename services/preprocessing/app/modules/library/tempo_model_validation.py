"""Resolve the held-out validation claim for BPM metrical-level selection."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


TEMPO_MODEL_VALIDATION_VERSION = "tempo_model_validation_v1"
DEFAULT_PATH = Path(__file__).parents[3] / "config" / "model_validation" / "tempo_consensus_v1.json"


@lru_cache(maxsize=2)
def load_tempo_model_validations(path: str | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_PATH
    if not target.is_file():
        return {"version": TEMPO_MODEL_VALIDATION_VERSION, "strategies": []}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("version") != TEMPO_MODEL_VALIDATION_VERSION:
        raise ValueError(f"unsupported tempo validation version: {payload.get('version')}")
    return payload


def resolve_tempo_model_validation(
    consensus: dict[str, Any],
    route_results: dict[str, dict],
    *,
    validations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reference_name = consensus.get("metrical_reference_engine")
    reference_engine = str((route_results.get(str(reference_name)) or {}).get("engine") or "")
    strategy = str(consensus.get("selection_strategy") or "")
    for entry in (validations or load_tempo_model_validations()).get("strategies", []):
        if (
            entry.get("selection_strategy") == strategy
            and entry.get("reference_route_engine") == reference_engine
        ):
            return {"status": "matched", "version": TEMPO_MODEL_VALIDATION_VERSION, **entry}
    return {
        "status": "unvalidated",
        "version": TEMPO_MODEL_VALIDATION_VERSION,
        "selection_strategy": strategy or None,
        "reference_route_engine": reference_engine or None,
    }
