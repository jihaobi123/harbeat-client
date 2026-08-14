"""Pure transition operation contract owned by the clean control plane."""

from __future__ import annotations

import copy
import hashlib
import json
from enum import Enum
from typing import Any, Mapping

from .orchestrator import OrchestrationValidationError


class TransitionIntent(str, Enum):
    AUTO = "auto"
    FAST = "fast"
    ENERGY = "energy"
    STYLE = "style"


class OperationStage(str, Enum):
    ACCEPTED = "accepted"
    SOURCE_SNAPSHOT = "source_snapshot"
    PLANNED = "planned"
    RENDERED_OR_REUSED = "rendered_or_reused"
    TARGET_AUDIO_READY = "target_audio_ready"
    PAIR_SYNCED = "pair_synced"
    PREPARED = "prepared"
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    RESUMED = "resumed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ORDERED_STAGES = (
    OperationStage.ACCEPTED,
    OperationStage.SOURCE_SNAPSHOT,
    OperationStage.PLANNED,
    OperationStage.RENDERED_OR_REUSED,
    OperationStage.TARGET_AUDIO_READY,
    OperationStage.PAIR_SYNCED,
    OperationStage.PREPARED,
    OperationStage.SCHEDULED,
    OperationStage.EXECUTING,
    OperationStage.RESUMED,
)


def validate_operation_request(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        intent = TransitionIntent(str(value.get("intent") or ""))
    except ValueError as exc:
        raise OrchestrationValidationError("invalid_intent") from exc
    request_id = _bounded_id(value.get("request_id"), "request_id", minimum=8)
    device_id = _bounded_id(value.get("device_id"), "device_id")
    session_id = _bounded_id(value.get("session_id"), "session_id")
    target_song_id = value.get("target_song_id")
    if intent in {TransitionIntent.ENERGY, TransitionIntent.STYLE} and target_song_id in (None, ""):
        raise OrchestrationValidationError("target_song_id_required")
    return {
        "device_id": device_id,
        "session_id": session_id,
        "intent": intent.value,
        "target_song_id": None if target_song_id in (None, "") else str(target_song_id),
        "request_id": request_id,
    }


def operation_request_hash(request: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(request), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def new_operation(
    request: Mapping[str, Any],
    *,
    operation_id: str,
    now: str,
) -> dict[str, Any]:
    normalized = validate_operation_request(request)
    return {
        "operation_id": _bounded_id(operation_id, "operation_id", minimum=8),
        **copy.deepcopy(normalized),
        "request_hash": operation_request_hash(normalized),
        "status": "active",
        "stage": OperationStage.ACCEPTED.value,
        "created_at": now,
        "updated_at": now,
        "source_snapshot": None,
        "plan": None,
        "render": None,
        "sync": None,
        "schedule": None,
        "result": None,
        "error": None,
        "events": [{"stage": OperationStage.ACCEPTED.value, "at": now}],
    }


def advance_operation(
    operation: Mapping[str, Any],
    stage: str,
    *,
    now: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    current = OperationStage(str(operation.get("stage") or ""))
    target = OperationStage(stage)
    if current in {OperationStage.RESUMED, OperationStage.FAILED, OperationStage.CANCELLED}:
        raise OrchestrationValidationError("operation_terminal")
    current_index = ORDERED_STAGES.index(current)
    if target != ORDERED_STAGES[current_index + 1]:
        raise OrchestrationValidationError(
            "invalid_operation_stage_transition",
            {"from": current.value, "to": target.value},
        )
    out = copy.deepcopy(dict(operation))
    out["stage"] = target.value
    out["updated_at"] = now
    if details:
        out[target.value] = copy.deepcopy(dict(details))
    out["events"] = [*list(out.get("events") or []), {"stage": target.value, "at": now}]
    if target is OperationStage.RESUMED:
        out["status"] = "succeeded"
    return out


def cancel_operation(operation: Mapping[str, Any], *, now: str) -> dict[str, Any]:
    current = OperationStage(str(operation.get("stage") or ""))
    if current in {OperationStage.RESUMED, OperationStage.FAILED, OperationStage.CANCELLED}:
        return copy.deepcopy(dict(operation))
    out = copy.deepcopy(dict(operation))
    out.update({"stage": "cancelled", "status": "cancelled", "updated_at": now})
    out["events"] = [*list(out.get("events") or []), {"stage": "cancelled", "at": now}]
    return out


def fail_operation(
    operation: Mapping[str, Any],
    *,
    now: str,
    failed_stage: str,
    code: str,
    retryable: bool,
    detail: str | None = None,
) -> dict[str, Any]:
    out = copy.deepcopy(dict(operation))
    out.update({
        "stage": "failed",
        "status": "failed",
        "updated_at": now,
        "error": {
            "stage": failed_stage,
            "code": code,
            "retryable": bool(retryable),
            "detail": detail,
        },
    })
    out["events"] = [*list(out.get("events") or []), {"stage": "failed", "at": now, "code": code}]
    return out


def public_operation(operation: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(dict(operation))
    out.pop("request_hash", None)
    return out


def _bounded_id(value: object, name: str, *, minimum: int = 1, maximum: int = 128) -> str:
    text = str(value or "").strip()
    if not minimum <= len(text) <= maximum:
        raise OrchestrationValidationError(f"invalid_{name}")
    return text
