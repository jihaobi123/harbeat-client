"""Cross-device operation timeline and conservative secret redaction."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .events import EventSource, EventStage, normalize_source, normalize_stage


SECRET_KEY = re.compile(r"(authorization|cookie|password|secret|token)", re.IGNORECASE)
BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return BEARER.sub("Bearer [REDACTED]", value)
    return value


@dataclass(frozen=True)
class TraceEvent:
    source: str
    stage: str
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalize_source(self.source)
        normalize_stage(self.stage)
        datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))

    @classmethod
    def now(cls, source: str, stage: str, **details: Any) -> "TraceEvent":
        return cls(
            source=source,
            stage=stage,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=redact(details),
        )


@dataclass
class OperationTrace:
    operation_id: str
    intent: str
    events: list[TraceEvent] = field(default_factory=list)

    def append(self, event: TraceEvent) -> None:
        self.events.append(
            TraceEvent(
                source=event.source,
                stage=event.stage,
                timestamp=event.timestamp,
                details=redact(event.details),
            )
        )

    def elapsed_seconds(self, start_stage: str, end_stage: str) -> float | None:
        start = next((event for event in self.events if event.stage == start_stage), None)
        end = next((event for event in reversed(self.events) if event.stage == end_stage), None)
        if start is None or end is None:
            return None
        started = datetime.fromisoformat(start.timestamp.replace("Z", "+00:00"))
        ended = datetime.fromisoformat(end.timestamp.replace("Z", "+00:00"))
        return round((ended - started).total_seconds(), 6)

    def to_report(self, *, passed: bool, error_code: str | None = None) -> dict:
        ordered = sorted(self.events, key=lambda event: event.timestamp)
        metrics = self.standard_metrics()
        return {
            "schema_version": 2,
            "operation_id": self.operation_id,
            "intent": self.intent,
            "events": [asdict(event) for event in ordered],
            "result": {
                "passed": passed,
                "error_code": error_code,
                "metrics": metrics,
            },
        }

    def standard_metrics(self) -> dict[str, float]:
        pairs = {
            "click_to_plan_sec": (EventStage.CLICKED.value, EventStage.PLANNED.value),
            "click_to_render_sec": (EventStage.CLICKED.value, EventStage.RENDERED.value),
            "sync_sec": (EventStage.SYNC_STARTED.value, EventStage.CACHE_READY.value),
            "click_to_scheduled_sec": (EventStage.CLICKED.value, EventStage.SCHEDULED.value),
            "click_to_transition_sec": (EventStage.CLICKED.value, EventStage.TRANSITION_STARTED.value),
            "transition_to_resume_sec": (EventStage.TRANSITION_STARTED.value, EventStage.RESUMED.value),
        }
        metrics = {}
        for name, (start, end) in pairs.items():
            value = self.elapsed_seconds(start, end)
            if value is not None:
                metrics[name] = value
        return metrics

