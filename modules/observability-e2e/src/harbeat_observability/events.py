"""Canonical sources and stages for cross-device operation traces."""

from __future__ import annotations

from enum import Enum


class EventSource(str, Enum):
    MOBILE = "mobile"
    JETSON = "jetson"
    RK_EDGE = "rk-edge"
    RK_SYNC = "rk-sync"
    RK_AUDIO = "rk-audio"
    TEST = "test"


class EventStage(str, Enum):
    CLICKED = "clicked"
    TARGET_SELECTED = "target_selected"
    PLANNED = "planned"
    RENDERED = "rendered"
    SYNC_STARTED = "sync_started"
    CACHE_READY = "cache_ready"
    PREPARED = "prepared"
    SCHEDULED = "scheduled"
    TRANSITION_STARTED = "transition_started"
    RESUMED = "resumed"
    COMPLETED = "completed"
    FAILED = "failed"


def normalize_source(value: str | EventSource) -> str:
    return EventSource(value).value


def normalize_stage(value: str | EventStage) -> str:
    return EventStage(value).value
