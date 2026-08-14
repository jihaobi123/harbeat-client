from __future__ import annotations

from harbeat_transition_orchestrator import (
    TransitionOperationExecutor,
    advance_operation,
    fail_operation,
    new_operation,
)


class Store:
    def __init__(self, operation: dict):
        self.operation = operation

    def get(self, operation_id: str):
        return dict(self.operation) if self.operation["operation_id"] == operation_id else None

    def advance(self, operation_id: str, stage: str, details=None):
        self.operation = advance_operation(self.operation, stage, now=stage, details=details)
        return dict(self.operation)

    def fail(self, operation_id: str, *, failed_stage: str, code: str, retryable: bool, detail=None):
        self.operation = fail_operation(
            self.operation,
            now="failed",
            failed_stage=failed_stage,
            code=code,
            retryable=retryable,
            detail=detail,
        )
        return dict(self.operation)


class Ports:
    def __init__(self):
        self.calls: list[str] = []
        self.states = [
            {"last_transition": {"transition_id": "operation-1234", "action": "default_render_playback"}},
            {
                "current_song_id": "song-b",
                "position_sec": 18.0,
                "last_transition": {"transition_id": "operation-1234", "action": "default_render_playback"},
            },
        ]

    def source_snapshot(self, operation):
        self.calls.append("snapshot")
        return {"current_song_id": "song-a", "next_song_id": "song-b", "position_sec": 4.0, "playing": True}

    def plan(self, operation, snapshot):
        self.calls.append("plan")
        return {"pair_id": "pair-a-b", "from_song_id": "song-a", "to_song_id": "song-b", "from_at_sec": 15.0, "to_at_sec": 12.0, "duration_sec": 4.0, "default_mix": {"pair_id": "pair-a-b"}}

    def render(self, operation, plan):
        self.calls.append("render")
        return {"pair_manifest": {"pair_id": "pair-a-b"}}

    def sync_target_audio(self, operation, target_song_id):
        self.calls.append("target")
        return {"song_id": target_song_id, "completed": 1, "total": 1}

    def sync_pair(self, operation, pair_manifest):
        self.calls.append("pair")
        return {"pair_id": pair_manifest["pair_id"], "completed": 2, "total": 2}

    def prepare(self, operation, plan):
        self.calls.append("prepare")
        return {"action": "default_render_prepared"}

    def schedule(self, operation, plan):
        self.calls.append("schedule")
        return {"action": "default_render_scheduled"}

    def playback_state(self):
        self.calls.append("state")
        return self.states.pop(0)


def operation(**changes):
    request = {
        "device_id": "rk3588-01",
        "session_id": "set-12345678",
        "intent": "fast",
        "target_song_id": None,
        "request_id": "request-12345678",
    }
    request.update(changes)
    return new_operation(request, operation_id="operation-1234", now="accepted")


def test_executor_runs_one_shared_pipeline_and_records_stage_details():
    store = Store(operation())
    ports = Ports()
    result = TransitionOperationExecutor(store, ports, poll_interval_sec=0.0).execute("operation-1234")

    assert result["status"] == "succeeded"
    assert result["stage"] == "resumed"
    assert result["plan"]["transition_id"] == "operation-1234"
    assert result["render"]["pair_manifest"]["pair_id"] == "pair-a-b"
    assert result["target_audio"]["song_id"] == "song-b"
    assert result["sync"]["completed"] == 2
    assert result["prepare"]["action"] == "default_render_prepared"
    assert result["schedule"]["action"] == "default_render_scheduled"
    assert result["execution"]["transition_id"] == "operation-1234"
    assert ports.calls[:2] == ["snapshot", "plan"]
    assert "render" in ports.calls and "target" in ports.calls


def test_executor_fails_explicitly_when_no_target_is_available():
    store = Store(operation())
    ports = Ports()
    ports.source_snapshot = lambda _operation: {"current_song_id": "song-a", "next_song_id": None}

    result = TransitionOperationExecutor(store, ports, poll_interval_sec=0.0).execute("operation-1234")

    assert result["status"] == "failed"
    assert result["error"]["stage"] == "source_snapshot"
    assert result["error"]["code"] == "target_song_unavailable"
