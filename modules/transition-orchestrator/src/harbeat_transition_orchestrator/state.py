"""Typed transition task states and legal state changes."""

from __future__ import annotations

from enum import Enum


class TaskState(str, Enum):
    ACCEPTED = "accepted"
    SYNCING = "syncing"
    CACHE_READY = "cache_ready"
    PREPARED = "prepared"
    PREWARMED = "prewarmed"
    SCHEDULED = "scheduled"
    EXECUTED = "executed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS = {
    TaskState.ACCEPTED: {TaskState.SYNCING, TaskState.CACHE_READY, TaskState.PREWARMED, TaskState.FAILED, TaskState.EXPIRED, TaskState.CANCELLED},
    TaskState.SYNCING: {TaskState.CACHE_READY, TaskState.FAILED, TaskState.EXPIRED, TaskState.CANCELLED},
    TaskState.CACHE_READY: {TaskState.PREPARED, TaskState.PREWARMED, TaskState.FAILED, TaskState.EXPIRED, TaskState.CANCELLED},
    TaskState.PREPARED: {TaskState.SCHEDULED, TaskState.FAILED, TaskState.EXPIRED, TaskState.CANCELLED},
    TaskState.SCHEDULED: {TaskState.EXECUTED},
    TaskState.PREWARMED: set(),
    TaskState.EXECUTED: set(),
    TaskState.FAILED: set(),
    TaskState.EXPIRED: set(),
    TaskState.CANCELLED: set(),
}

TERMINAL_STATES = frozenset(state.value for state, targets in ALLOWED_TRANSITIONS.items() if not targets)
ACTIVE_STATES = frozenset({TaskState.ACCEPTED.value, TaskState.SYNCING.value, TaskState.CACHE_READY.value, TaskState.PREPARED.value})


def parse_state(value: object) -> TaskState:
    try:
        return TaskState(str(value))
    except ValueError as exc:
        raise ValueError(f"unknown task state: {value}") from exc
