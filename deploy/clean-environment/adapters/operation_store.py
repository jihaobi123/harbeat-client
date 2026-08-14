"""Atomic JSON persistence for clean transition operations."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from harbeat_transition_orchestrator import (
    OrchestrationValidationError,
    advance_operation,
    cancel_operation,
    fail_operation,
    new_operation,
    operation_request_hash,
    public_operation,
    validate_operation_request,
)


class JsonOperationStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def create_or_reuse(self, request: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        normalized = validate_operation_request(request)
        request_key = self._request_key(normalized)
        request_hash = operation_request_hash(normalized)
        with self._lock:
            payload = self._load()
            existing_id = payload["request_index"].get(request_key)
            if existing_id:
                existing = payload["operations"][existing_id]
                if existing.get("request_hash") != request_hash:
                    raise OrchestrationValidationError("request_id_conflict")
                return public_operation(existing), True
            operation = new_operation(
                normalized,
                operation_id=str(uuid.uuid4()),
                now=self._now(),
            )
            payload["operations"][operation["operation_id"]] = operation
            payload["request_index"][request_key] = operation["operation_id"]
            self._save(payload)
            return public_operation(operation), False

    def get(self, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            operation = self._load()["operations"].get(operation_id)
            return public_operation(operation) if operation else None

    def cancel(self, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            payload = self._load()
            operation = payload["operations"].get(operation_id)
            if operation is None:
                return None
            cancelled = cancel_operation(operation, now=self._now())
            payload["operations"][operation_id] = cancelled
            self._save(payload)
            return public_operation(cancelled)

    def advance(
        self,
        operation_id: str,
        stage: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            payload = self._load()
            operation = payload["operations"].get(operation_id)
            if operation is None:
                raise OrchestrationValidationError("operation_not_found")
            updated = advance_operation(operation, stage, now=self._now(), details=details)
            payload["operations"][operation_id] = updated
            self._save(payload)
            return public_operation(updated)

    def fail(
        self,
        operation_id: str,
        *,
        failed_stage: str,
        code: str,
        retryable: bool,
        detail: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            payload = self._load()
            operation = payload["operations"].get(operation_id)
            if operation is None:
                raise OrchestrationValidationError("operation_not_found")
            updated = fail_operation(
                operation,
                now=self._now(),
                failed_stage=failed_stage,
                code=code,
                retryable=retryable,
                detail=detail,
            )
            payload["operations"][operation_id] = updated
            self._save(payload)
            return public_operation(updated)

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.is_file():
            return {"operations": {}, "request_index": {}}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("operation store must contain an object")
        return {
            "operations": dict(value.get("operations") or {}),
            "request_index": dict(value.get("request_index") or {}),
        }

    def _save(self, value: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _request_key(request: Mapping[str, Any]) -> str:
        return "|".join(str(request[name]) for name in ("device_id", "session_id", "request_id"))

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
