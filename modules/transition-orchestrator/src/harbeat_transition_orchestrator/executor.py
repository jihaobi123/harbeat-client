"""Server-owned execution of one persisted transition operation."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class OperationStorePort(Protocol):
    def get(self, operation_id: str) -> dict[str, Any] | None: ...

    def advance(
        self,
        operation_id: str,
        stage: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def fail(
        self,
        operation_id: str,
        *,
        failed_stage: str,
        code: str,
        retryable: bool,
        detail: str | None = None,
    ) -> dict[str, Any]: ...


class OperationPorts(Protocol):
    def source_snapshot(self, operation: Mapping[str, Any]) -> dict[str, Any]: ...
    def plan(self, operation: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]: ...
    def render(self, operation: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]: ...
    def sync_target_audio(self, operation: Mapping[str, Any], target_song_id: str) -> dict[str, Any]: ...
    def sync_pair(self, operation: Mapping[str, Any], pair_manifest: Mapping[str, Any]) -> dict[str, Any]: ...
    def prepare(self, operation: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]: ...
    def schedule(self, operation: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]: ...
    def playback_state(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class OperationExecutionError(RuntimeError):
    stage: str
    code: str
    retryable: bool
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(slots=True)
class TransitionOperationExecutor:
    store: OperationStorePort
    ports: OperationPorts
    monitor_timeout_sec: float = 90.0
    poll_interval_sec: float = 0.1

    def execute(self, operation_id: str) -> dict[str, Any]:
        try:
            operation = self._active(operation_id)
            snapshot = self.ports.source_snapshot(operation)
            target_song_id = self._target_song_id(operation, snapshot)
            snapshot = {**snapshot, "target_song_id": target_song_id}
            operation = self.store.advance(operation_id, "source_snapshot", snapshot)

            plan = self.ports.plan(operation, snapshot)
            plan = {**plan, "transition_id": operation_id}
            operation = self.store.advance(operation_id, "planned", plan)

            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="transition-operation") as pool:
                render_future = pool.submit(self.ports.render, operation, plan)
                target_future = pool.submit(self.ports.sync_target_audio, operation, target_song_id)
                try:
                    render = render_future.result()
                except OperationExecutionError:
                    raise
                except Exception as exc:
                    raise OperationExecutionError("rendered_or_reused", "render_failed", True, str(exc)) from exc
                operation = self.store.advance(operation_id, "rendered_or_reused", render)
                try:
                    target_audio = target_future.result()
                except OperationExecutionError:
                    raise
                except Exception as exc:
                    raise OperationExecutionError("target_audio_ready", "target_sync_failed", True, str(exc)) from exc
            operation = self.store.advance(operation_id, "target_audio_ready", target_audio)

            pair_manifest = render.get("pair_manifest")
            if not isinstance(pair_manifest, Mapping):
                raise OperationExecutionError(
                    "pair_synced", "pair_manifest_missing", False, "renderer returned no pair manifest"
                )
            pair_sync = self.ports.sync_pair(operation, pair_manifest)
            operation = self.store.advance(operation_id, "pair_synced", pair_sync)

            prepared = self.ports.prepare(operation, plan)
            operation = self.store.advance(operation_id, "prepared", prepared)
            scheduled = self.ports.schedule(operation, plan)
            self.store.advance(operation_id, "scheduled", scheduled)
            return self._monitor(operation_id, target_song_id)
        except OperationExecutionError as exc:
            current = self.store.get(operation_id)
            if current is not None and current.get("status") != "active":
                return current
            return self.store.fail(
                operation_id,
                failed_stage=exc.stage,
                code=exc.code,
                retryable=exc.retryable,
                detail=exc.detail,
            )
        except Exception as exc:
            current = self.store.get(operation_id) or {}
            return self.store.fail(
                operation_id,
                failed_stage=str(current.get("stage") or "accepted"),
                code="unexpected_execution_error",
                retryable=False,
                detail=str(exc),
            )

    def _monitor(self, operation_id: str, target_song_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.monitor_timeout_sec
        executing = False
        while time.monotonic() < deadline:
            self._active(operation_id)
            state = self.ports.playback_state()
            last = state.get("last_transition") if isinstance(state.get("last_transition"), Mapping) else {}
            matching = str(last.get("transition_id") or "") == operation_id
            if matching and last.get("action") == "default_render_playback" and not executing:
                self.store.advance(operation_id, "executing", dict(last))
                executing = True
            if executing and str(state.get("current_song_id") or "") == target_song_id:
                return self.store.advance(operation_id, "resumed", {
                    "current_song_id": target_song_id,
                    "position_sec": state.get("position_sec"),
                    "last_transition": dict(last),
                })
            time.sleep(self.poll_interval_sec)
        raise OperationExecutionError(
            "executing" if executing else "scheduled",
            "playback_monitor_timeout",
            True,
            "timed out waiting for rendered playback and target resume",
        )

    def _active(self, operation_id: str) -> dict[str, Any]:
        operation = self.store.get(operation_id)
        if operation is None:
            raise OperationExecutionError("accepted", "operation_not_found", False, operation_id)
        if operation.get("status") != "active":
            raise OperationExecutionError(
                str(operation.get("stage") or "accepted"),
                "operation_not_active",
                False,
                f"operation is {operation.get('status')}",
            )
        return operation

    @staticmethod
    def _target_song_id(operation: Mapping[str, Any], snapshot: Mapping[str, Any]) -> str:
        target = operation.get("target_song_id") or snapshot.get("next_song_id")
        if target in (None, ""):
            raise OperationExecutionError(
                "source_snapshot", "target_song_unavailable", False, "operation has no target song"
            )
        if str(target) == str(snapshot.get("current_song_id") or ""):
            raise OperationExecutionError(
                "source_snapshot", "self_transition_rejected", False, "target equals current song"
            )
        return str(target)
