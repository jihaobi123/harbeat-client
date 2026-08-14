"""Concrete clean edge ports for a persisted transition operation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import httpx

from harbeat_transition_orchestrator import (
    OperationExecutionError,
    validate_request,
)

from .config import AdapterConfig
from .rk_app import _audio_command


class HttpOperationPorts:
    def __init__(self, config: AdapterConfig) -> None:
        self.config = config
        self.timeout = httpx.Timeout(connect=3.0, read=30.0, write=15.0, pool=3.0)

    def source_snapshot(self, _operation: Mapping[str, Any]) -> dict[str, Any]:
        try:
            state = _audio_command(str(self.config.settings["audio_socket"]), {"cmd": "state"})
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            raise OperationExecutionError("source_snapshot", "audio_runtime_unreachable", True, str(exc)) from exc
        if state.get("ok") is False or not state.get("playing") or state.get("paused"):
            raise OperationExecutionError("source_snapshot", "source_not_playing", True, "audio runtime is not playing")
        if state.get("current_song_id") in (None, ""):
            raise OperationExecutionError("source_snapshot", "source_song_unavailable", True, "audio runtime has no current song")
        return {
            "current_song_id": str(state["current_song_id"]),
            "next_song_id": None if state.get("next_song_id") in (None, "") else str(state["next_song_id"]),
            "position_sec": float(state.get("position_sec") or 0.0),
            "duration_sec": state.get("duration_sec"),
            "playing": True,
        }

    def plan(self, operation: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
        intent = str(operation["intent"])
        # Once the target is known, all four intents use the verified v2/v7
        # live-window path. They differ only in how the target was selected.
        mode = "fast"
        cursor = float(snapshot["position_sec"])
        options: dict[str, Any] = {"cursor_sec": cursor}
        if mode == "fast":
            options.update({
                "min_exit_sec": cursor + float(self.config.settings.get("fast_min_lead_sec", 12.0)),
                "max_exit_sec": cursor + float(self.config.settings.get("fast_max_lead_sec", 15.0)),
                "render_budget_sec": float(self.config.settings.get("fast_render_budget_sec", 10.0)),
                "require_precomputed_v2": True,
            })
        return self._post(
            "planned",
            self.config.settings["planning_api_url"],
            "/planning/database/transition",
            {
                "from_song_id": snapshot["current_song_id"],
                "to_song_id": snapshot["target_song_id"],
                "mode": mode,
                "options": options,
            },
        )

    def render(self, operation: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
        result = self._post(
            "rendered_or_reused",
            self.config.settings["render_worker_url"],
            "/render/database/transition",
            {
                "from_song_id": plan["from_song_id"],
                "to_song_id": plan["to_song_id"],
                "plan": dict(plan),
            },
        )
        manifest = result.get("pair_manifest")
        if not isinstance(manifest, Mapping):
            raise OperationExecutionError("rendered_or_reused", "pair_manifest_missing", False, "renderer returned no pair manifest")
        try:
            validate_request(
                transition_id=str(operation["operation_id"]),
                trigger={
                    "fast": "fast_cut",
                    "energy": "energy_cut",
                    "style": "style_cut",
                    "auto": "fast_cut",
                }[str(operation["intent"])],
                from_song_id=plan["from_song_id"],
                to_song_id=plan["to_song_id"],
                transition_plan=plan,
                pair_manifest=manifest,
            )
        except Exception as exc:
            raise OperationExecutionError("rendered_or_reused", "render_contract_invalid", False, str(exc)) from exc
        return {**result, "pair_manifest": self._absolute_manifest_urls(manifest)}

    def sync_target_audio(self, operation: Mapping[str, Any], target_song_id: str) -> dict[str, Any]:
        manifest = self._post(
            "target_audio_ready",
            self.config.settings["render_worker_url"],
            f"/render/database/song/{target_song_id}/manifest",
            None,
            method="GET",
        )
        return self._sync(
            "target_audio_ready",
            {"plan_id": operation["operation_id"], "tracks": [self._absolute_manifest_urls(manifest)]},
        )

    def sync_pair(self, operation: Mapping[str, Any], pair_manifest: Mapping[str, Any]) -> dict[str, Any]:
        plan = operation.get("plan") if isinstance(operation.get("plan"), Mapping) else {}
        request = {
            "plan_id": operation["operation_id"],
            "tracks": [],
            "default_mix_pairs": [self._absolute_manifest_urls(pair_manifest)],
            "priority": True,
            "wait": True,
        }
        return self._sync("pair_synced", request)

    def prepare(self, operation: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
        return self._audio("prepared", {
            "cmd": "prepare_default_render",
            "transition_plan": dict(plan),
            "to_song_id": plan["to_song_id"],
            "render_path": str(self._render_path(plan)),
        })

    def schedule(self, operation: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
        return self._audio("scheduled", {
            "cmd": "schedule_default_render",
            "transition_plan": dict(plan),
            "to_song_id": plan["to_song_id"],
            "render_path": str(self._render_path(plan)),
            "min_lead_sec": float(self.config.settings.get("schedule_min_lead_sec", 1.5)),
        })

    def playback_state(self) -> dict[str, Any]:
        return self._audio("executing", {"cmd": "state"})

    def _sync(self, stage: str, body: Mapping[str, Any]) -> dict[str, Any]:
        result = self._post(stage, self.config.settings["sync_worker_url"], "/sync", dict(body))
        status = result.get("status") if isinstance(result.get("status"), Mapping) else {}
        if not result.get("ok") or status.get("errors") or not result.get("sync_completed"):
            raise OperationExecutionError(stage, "asset_sync_incomplete", True, str(result))
        return {
            "completed": status.get("completed"),
            "total": status.get("total"),
            "file_timings": status.get("file_timings"),
        }

    def _audio(self, stage: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            result = _audio_command(str(self.config.settings["audio_socket"]), dict(payload))
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            raise OperationExecutionError(stage, "audio_runtime_unreachable", True, str(exc)) from exc
        if result.get("ok") is False:
            raise OperationExecutionError(stage, "audio_runtime_rejected", True, str(result.get("error") or result))
        return result

    def _post(
        self,
        stage: str,
        base_url: object,
        path: str,
        body: Mapping[str, Any] | None,
        *,
        method: str = "POST",
    ) -> dict[str, Any]:
        url = self._url(base_url, path)
        try:
            response = httpx.request(method, url, json=None if body is None else dict(body), timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OperationExecutionError(stage, "remote_request_failed", True, f"{method} {url}: {exc}") from exc
        if not isinstance(payload, dict):
            raise OperationExecutionError(stage, "remote_payload_invalid", True, f"{method} {url} returned non-object")
        return payload

    def _absolute_manifest_urls(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(manifest)
        files = result.get("files") if isinstance(result.get("files"), Mapping) else {}
        result["files"] = {
            name: {
                **dict(spec),
                "url": self._url(self.config.settings["render_worker_url"], str(spec.get("url") or "")),
            }
            for name, spec in files.items()
            if isinstance(spec, Mapping)
        }
        return result

    def _render_path(self, plan: Mapping[str, Any]) -> Path:
        pair_id = str(plan.get("pair_id") or "")
        safe = "".join(char for char in pair_id if char.isalnum() or char in "-_")
        if not safe or safe != pair_id:
            raise OperationExecutionError("prepared", "invalid_pair_id", False, pair_id)
        return Path(str(self.config.settings["runtime_home"])) / "cache" / "default-mix" / "pairs" / safe / "transition_render.wav"

    @staticmethod
    def _url(base_url: object, path: str) -> str:
        base = str(base_url or "").rstrip("/")
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not base:
            raise OperationExecutionError("accepted", "service_url_missing", False, "service URL is missing")
        return f"{base}/{path.lstrip('/')}"
