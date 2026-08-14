"""Device-neutral manual transition orchestration protocol."""

from .orchestrator import (
    OrchestrationValidationError,
    TERMINAL_STATES,
    accept_or_reuse,
    accept_task,
    build_priority_sync_request,
    public_task,
    transition_task,
    validate_request,
)
from .state import ACTIVE_STATES, TaskState
from .operation import (
    OperationStage,
    TransitionIntent,
    advance_operation,
    cancel_operation,
    fail_operation,
    new_operation,
    operation_request_hash,
    public_operation,
    validate_operation_request,
)
from .executor import OperationExecutionError, TransitionOperationExecutor

__all__ = [
    "OrchestrationValidationError",
    "ACTIVE_STATES",
    "TaskState",
    "TERMINAL_STATES",
    "accept_task",
    "accept_or_reuse",
    "OperationStage",
    "TransitionIntent",
    "advance_operation",
    "cancel_operation",
    "fail_operation",
    "new_operation",
    "operation_request_hash",
    "public_operation",
    "validate_operation_request",
    "OperationExecutionError",
    "TransitionOperationExecutor",
    "build_priority_sync_request",
    "public_task",
    "transition_task",
    "validate_request",
]
