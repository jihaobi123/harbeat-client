"""Session binding rules for device-scoped operation recovery."""

from __future__ import annotations

from dataclasses import dataclass

from .operation import OperationRef
from .state import RuntimeSession


@dataclass(frozen=True, slots=True)
class SessionBinding:
    session: RuntimeSession

    def accepts(self, operation: OperationRef, now_ms: int) -> bool:
        return (
            self.session.is_valid(now_ms)
            and not operation.is_expired(now_ms)
            and operation.device_id == self.session.device_id
            and operation.session_id == self.session.session_id
        )

    def require(self, operation: OperationRef, now_ms: int) -> None:
        if not self.accepts(operation, now_ms):
            raise ValueError("operation does not belong to the active device session")
