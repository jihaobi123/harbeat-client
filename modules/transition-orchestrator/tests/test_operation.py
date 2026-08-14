import pytest

from harbeat_transition_orchestrator import (
    OrchestrationValidationError,
    advance_operation,
    cancel_operation,
    fail_operation,
    new_operation,
    public_operation,
    validate_operation_request,
)


def request(**changes):
    value = {
        "device_id": "rk3588-01",
        "session_id": "set-12345678",
        "intent": "fast",
        "target_song_id": None,
        "request_id": "request-12345678",
    }
    value.update(changes)
    return value


def test_operation_request_requires_target_only_for_preview_intents():
    assert validate_operation_request(request())["intent"] == "fast"
    assert validate_operation_request(request(intent="auto"))["target_song_id"] is None
    with pytest.raises(OrchestrationValidationError, match="target_song_id_required"):
        validate_operation_request(request(intent="energy"))
    assert validate_operation_request(request(intent="style", target_song_id="song-b"))["target_song_id"] == "song-b"


def test_operation_advances_in_one_deterministic_order():
    operation = new_operation(request(), operation_id="operation-1234", now="t0")
    for index, stage in enumerate((
        "source_snapshot",
        "planned",
        "rendered_or_reused",
        "target_audio_ready",
        "pair_synced",
        "prepared",
        "scheduled",
        "executing",
        "resumed",
    ), start=1):
        operation = advance_operation(operation, stage, now=f"t{index}")
    assert operation["status"] == "succeeded"
    assert operation["stage"] == "resumed"
    assert len(operation["events"]) == 10
    with pytest.raises(OrchestrationValidationError, match="operation_terminal"):
        advance_operation(operation, "resumed", now="later")


def test_operation_cancel_and_failure_are_typed_and_public_safe():
    operation = new_operation(request(), operation_id="operation-1234", now="t0")
    failed = fail_operation(
        operation,
        now="t1",
        failed_stage="planned",
        code="planner_timeout",
        retryable=True,
    )
    assert failed["error"] == {
        "stage": "planned",
        "code": "planner_timeout",
        "retryable": True,
        "detail": None,
    }
    cancelled = cancel_operation(operation, now="t1")
    assert cancelled["status"] == "cancelled"
    assert "request_hash" not in public_operation(cancelled)
