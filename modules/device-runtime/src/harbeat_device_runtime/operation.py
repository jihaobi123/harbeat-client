"""Compact, short-lived references for mobile operations."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import Enum


class OperationStatus(str, Enum):
  CREATED = "created"
  SUBMITTED = "submitted"
  PREPARED = "prepared"
  SCHEDULED = "scheduled"
  COMPLETED = "completed"
  FAILED = "failed"
  EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class OperationRef:
  operation_id: str
  device_id: str
  session_id: str
  kind: str
  created_at_ms: int
  expires_at_ms: int
  status: OperationStatus = OperationStatus.CREATED

  @classmethod
  def create(
    cls,
    *,
    device_id: str,
    session_id: str,
    kind: str,
    now_ms: int | None = None,
    ttl_ms: int = 120_000,
  ) -> "OperationRef":
    now = int(time.time() * 1000) if now_ms is None else now_ms
    if not device_id or not session_id or not kind:
      raise ValueError("device_id, session_id, and kind are required")
    if ttl_ms <= 0:
      raise ValueError("operation TTL must be positive")
    return cls(
      operation_id=f"op-{uuid.uuid4().hex}",
      device_id=device_id,
      session_id=session_id,
      kind=kind,
      created_at_ms=now,
      expires_at_ms=now + ttl_ms,
    )

  def is_expired(self, now_ms: int) -> bool:
    return now_ms >= self.expires_at_ms

  def compact(self) -> dict[str, object]:
    return {
      "operation_id": self.operation_id,
      "device_id": self.device_id,
      "session_id": self.session_id,
      "kind": self.kind,
      "created_at_ms": self.created_at_ms,
      "expires_at_ms": self.expires_at_ms,
      "status": self.status.value,
    }
