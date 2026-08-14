from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(REPO_ROOT / "modules" / "transition-orchestrator" / "src"))

from adapters.operation_store import JsonOperationStore
from harbeat_transition_orchestrator import OrchestrationValidationError


def request(**changes):
    value = {
        "device_id": "rk3588-01",
        "session_id": "set-12345678",
        "intent": "energy",
        "target_song_id": "song-b",
        "request_id": "request-12345678",
    }
    value.update(changes)
    return value


def test_store_reuses_request_across_instances_and_persists_cancel(tmp_path: Path):
    path = tmp_path / "operations.json"
    first, reused = JsonOperationStore(path).create_or_reuse(request())
    assert reused is False

    second, reused = JsonOperationStore(path).create_or_reuse(request())
    assert reused is True
    assert second["operation_id"] == first["operation_id"]
    assert "request_hash" not in second

    cancelled = JsonOperationStore(path).cancel(first["operation_id"])
    assert cancelled["status"] == "cancelled"
    assert JsonOperationStore(path).get(first["operation_id"])["status"] == "cancelled"


def test_store_rejects_same_request_id_with_different_content(tmp_path: Path):
    store = JsonOperationStore(tmp_path / "operations.json")
    store.create_or_reuse(request())
    with pytest.raises(OrchestrationValidationError, match="request_id_conflict"):
        store.create_or_reuse(request(target_song_id="song-c"))
