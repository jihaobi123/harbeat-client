from __future__ import annotations

import asyncio
import copy
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from fastapi import FastAPI, HTTPException

from harbeat_transition_orchestrator import (
    OrchestrationValidationError,
    accept_or_reuse,
    build_priority_sync_request,
    public_task,
    transition_task,
    validate_request,
)

from .config import AdapterConfig

AudioCommand = Callable[[str, dict[str, Any]], dict[str, Any]]


class EdgeRuntime:
    """Thin transport adapter over the clean audio, sync and orchestration modules."""

    def __init__(self, config: AdapterConfig, audio_command: AudioCommand) -> None:
        self.config = config
        self.audio_socket = str(config.settings["audio_socket"])
        self.sync_worker_url = str(config.settings["sync_worker_url"]).rstrip("/")
        self.audio_command = audio_command
        self.tasks: dict[str, dict[str, Any]] = {}
        self.runners: dict[str, asyncio.Task[None]] = {}
        self.tasks_path = config.state_root / "transition-tasks.json"
        self._lock = asyncio.Lock()
        self._load_tasks()

    def command(self, cmd: str, **payload: Any) -> dict[str, Any]:
        try:
            result = self.audio_command(self.audio_socket, {"cmd": cmd, **payload})
        except (OSError, RuntimeError, json.JSONDecodeError, AttributeError) as exc:
            raise HTTPException(status_code=503, detail=f"audio runtime unavailable: {exc}") from exc
        if result.get("ok") is False:
            code = int(result.get("code") or 503)
            raise HTTPException(status_code=code, detail=result.get("error") or "audio runtime rejected command")
        return result

    async def command_async(self, cmd: str, **payload: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self.command, cmd, **payload)

    async def http_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: float = 3.0,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, f"{self.sync_worker_url}{path}", json=body)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("sync worker returned a non-object response")
        return payload

    async def set_task(self, transition_id: str, state: str, **changes: Any) -> dict[str, Any]:
        async with self._lock:
            current = self.tasks[transition_id]
            updated = transition_task(current, state, **changes)
            updated["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.tasks[transition_id] = updated
            self._save_tasks()
            return copy.deepcopy(updated)

    async def reconcile_task(self, transition_id: str) -> dict[str, Any] | None:
        task = self.tasks.get(transition_id)
        if task is None or task.get("state") != "scheduled":
            return task
        state = await self.command_async("state")
        last = state.get("last_transition") if isinstance(state.get("last_transition"), dict) else {}
        executed = str(last.get("transition_id") or "") == transition_id and str(
            last.get("action") or ""
        ) in {"default_render_playback", "default_render_resume"}
        if executed:
            return await self.set_task(transition_id, "executed")
        return task

    async def pair_ready(self, pair_id: str) -> bool:
        payload = await self.http_json("GET", f"/cache/check?pair_id={pair_id}", timeout=1.0)
        return payload.get("exists") is True

    def normalize(self, body: dict[str, Any]) -> dict[str, Any]:
        pair_manifest = body.get("default_mix_pair_manifest") or body.get("pair_manifest") or {}
        try:
            return validate_request(
                transition_id=str(body.get("transition_id") or ""),
                trigger=str(body.get("trigger") or ""),
                from_song_id=body.get("from_song_id"),
                to_song_id=body.get("to_song_id"),
                transition_plan=body.get("transition_plan") or {},
                pair_manifest=pair_manifest,
                mode=str(body.get("mode") or "schedule"),
                min_lead_sec=float(body.get("min_lead_sec") or 1.5),
            )
        except (OrchestrationValidationError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail={"code": getattr(exc, "code", "invalid_request"), "message": str(exc)}) from exc

    async def accept(self, body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        request = self.normalize(body)
        transition_id = request["transition_id"]
        state = await self.command_async("state")
        if state.get("playing") is not True or str(state.get("current_song_id")) != request["from_song_id"]:
            raise HTTPException(
                status_code=409,
                detail={"code": "source_song_changed", "actual": state.get("current_song_id")},
            )
        remaining = request["planned_from_at_sec"] - float(state.get("position_sec") or 0.0)
        if remaining <= request["min_lead_sec"]:
            raise HTTPException(status_code=409, detail={"code": "insufficient_lead_at_accept"})
        try:
            task, reused = accept_or_reuse(
                request,
                self.tasks.get(transition_id),
                now=datetime.now(timezone.utc).isoformat(),
                deadline_epoch_sec=time.time() + remaining - request["min_lead_sec"],
            )
        except OrchestrationValidationError as exc:
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
        if reused:
            return task, True
        task["accepted_position_sec"] = float(state.get("position_sec") or 0.0)
        self.tasks[transition_id] = task
        self._save_tasks()
        runner = asyncio.create_task(self.run(request))
        self.runners[transition_id] = runner
        runner.add_done_callback(lambda _task: self.runners.pop(transition_id, None))
        return task, False

    async def run(self, request: dict[str, Any]) -> None:
        transition_id = request["transition_id"]
        started = time.monotonic()
        try:
            if not await self.pair_ready(request["pair_id"]):
                await self.set_task(transition_id, "syncing")
                sync_request = build_priority_sync_request(request)
                response = await self.http_json("POST", "/sync", body=sync_request)
                if response.get("ok") is not True:
                    raise RuntimeError(f"sync rejected: {response}")
                while not await self.pair_ready(request["pair_id"]):
                    if time.time() >= float(self.tasks[transition_id]["deadline_epoch_sec"]):
                        await self._fail(transition_id, "expired", "sync_deadline_expired")
                        return
                    await asyncio.sleep(0.05)
            sync_sec = round(time.monotonic() - started, 4)
            await self.set_task(transition_id, "cache_ready", timings={"rk_sync_sec": sync_sec})
            if request["mode"] == "prewarm":
                await self.set_task(
                    transition_id,
                    "prewarmed",
                    result=self._result(request, "default_render_prewarmed"),
                    error=None,
                )
                return
            await self._assert_source_and_lead(request)
            plan = copy.deepcopy(request["transition_plan"])
            plan["transition_id"] = transition_id
            prepare_started = time.monotonic()
            prepared = await self.command_async(
                "prepare_default_render",
                transition_plan=plan,
                to_song_id=request["to_song_id"],
            )
            timings = dict(self.tasks[transition_id].get("timings") or {})
            timings["prepare_sec"] = round(time.monotonic() - prepare_started, 4)
            await self.set_task(transition_id, "prepared", timings=timings)
            await self._assert_source_and_lead(request)
            schedule_started = time.monotonic()
            result = await self.command_async(
                "schedule_default_render",
                transition_plan=plan,
                to_song_id=request["to_song_id"],
                min_lead_sec=request["min_lead_sec"],
            )
            if result.get("action") != "default_render_scheduled" or result.get("degraded") is True:
                raise RuntimeError(f"schedule rejected: {result}")
            timings = dict(self.tasks[transition_id].get("timings") or {})
            timings["schedule_sec"] = round(time.monotonic() - schedule_started, 4)
            await self.set_task(transition_id, "scheduled", result=result, timings=timings, error=None)
        except asyncio.CancelledError:
            current = self.tasks.get(transition_id)
            if current and current.get("state") not in {"scheduled", "executed", "cancelled"}:
                await self._fail(transition_id, "cancelled", "cancelled")
            raise
        except Exception as exc:
            current = self.tasks.get(transition_id)
            if current and current.get("state") not in {"expired", "cancelled", "failed"}:
                await self._fail(transition_id, "failed", "orchestration_failed", str(exc))

    async def _assert_source_and_lead(self, request: dict[str, Any]) -> float:
        state = await self.command_async("state")
        if state.get("playing") is not True:
            raise RuntimeError("playback_not_active")
        if str(state.get("current_song_id")) != request["from_song_id"]:
            raise RuntimeError("source_song_changed")
        remaining = request["planned_from_at_sec"] - float(state.get("position_sec") or 0.0)
        if remaining < request["min_lead_sec"]:
            raise RuntimeError("insufficient_lead")
        return remaining

    async def _fail(self, transition_id: str, state: str, code: str, detail: Any = None) -> None:
        await self.set_task(transition_id, state, error={"code": code, "detail": detail})

    @staticmethod
    def _result(request: dict[str, Any], action: str) -> dict[str, Any]:
        return {
            "ok": True,
            "action": action,
            "transition_id": request["transition_id"],
            "pair_id": request["pair_id"],
            "from_song_id": request["from_song_id"],
            "to_song_id": request["to_song_id"],
            "planned_from_at_sec": request["planned_from_at_sec"],
            "playback_tier": "default_render_playback",
            "degraded": False,
        }

    def _load_tasks(self) -> None:
        try:
            payload = json.loads(self.tasks_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                self.tasks = {str(key): value for key, value in payload.items() if isinstance(value, dict)}
        except (OSError, json.JSONDecodeError):
            self.tasks = {}

    def _save_tasks(self) -> None:
        self.tasks_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.tasks_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.tasks, ensure_ascii=True, indent=2), encoding="utf-8")
        temporary.replace(self.tasks_path)


def install_edge_routes(app: FastAPI, config: AdapterConfig, audio_command: AudioCommand) -> None:
    runtime = EdgeRuntime(config, audio_command)
    app.state.edge_runtime = runtime
    protocol_tasks: dict[str, dict[str, Any]] = {}

    def wrapped(cmd: str, **payload: Any) -> dict[str, Any]:
        return {"ok": True, "result": runtime.command(cmd, **payload)}

    @app.get("/state")
    @app.get("/api/edge/status")
    @app.get("/autoplay/default/state")
    def state() -> dict[str, Any]:
        return runtime.command("state")

    @app.post("/play")
    def play(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("play", song_id=body.get("song_id"), start_at_sec=float(body.get("start_at_sec") or 0.0), load_stems=bool(body.get("load_stems", True)))

    @app.post("/pause")
    def pause() -> dict[str, Any]:
        return wrapped("pause")

    @app.post("/resume")
    def resume() -> dict[str, Any]:
        return wrapped("resume")

    @app.post("/next")
    def next_track() -> dict[str, Any]:
        return wrapped("next")

    @app.post("/seek")
    def seek(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("seek", sec=float(body.get("sec") or 0.0))

    @app.post("/stem_solo")
    def stem_solo(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("stem_solo", stem=body.get("stem"))

    @app.post("/trigger")
    def trigger(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("trigger", key=int(body.get("key")))

    @app.post("/prefetch")
    def prefetch(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("prefetch", song_ids=body.get("song_ids") or [], wait=bool(body.get("wait", False)), load_stems=bool(body.get("load_stems", True)))

    @app.post("/cache/validate")
    def validate_cache(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("validate_cache", song_ids=body.get("song_ids") or [], require_stems=bool(body.get("require_stems", False)))

    @app.post("/prewarm_beatmatch")
    def prewarm_beatmatch(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("prewarm_beatmatch", song_id=body.get("song_id"), tempo_ratio=body.get("tempo_ratio"), tempo_multiplier=body.get("tempo_multiplier"))

    @app.post("/beat_reinforce")
    def beat_reinforce(body: dict[str, Any]) -> dict[str, Any]:
        return runtime.command("beat_reinforce", **body)

    @app.post("/xfade")
    @app.post("/xfade_mix_effects")
    def xfade(body: dict[str, Any]) -> dict[str, Any]:
        command = "xfade_eq_band_mix" if body.get("transition_mode") == "eq_band_mix" and body.get("transition_plan") else "xfade"
        result = runtime.command(command, **body)
        return {"ok": True, "actual_tier": result.get("playback_tier"), "degraded": bool(result.get("degraded", False)), "result": result}

    @app.post("/autoplay/default/start")
    def autoplay_start(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("default_autoplay_start", queue=body.get("queue") or [], transitions=body.get("transitions") or [], start_song_id=body.get("start_song_id"), start_at_sec=float(body.get("start_at_sec") or 0.0), session_id=body.get("session_id"))

    @app.post("/autoplay/default/prefetch")
    def autoplay_prefetch(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("default_autoplay_prefetch", queue=body.get("queue") or [], transitions=body.get("transitions") or [], session_id=body.get("session_id"))

    def render_payload(body: dict[str, Any]) -> dict[str, Any]:
        return {"transition_plan": body.get("transition_plan") or {}, "to_song_id": body.get("to_song_id"), "render_path": body.get("render_path")}

    @app.post("/autoplay/default/render")
    def render(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("default_render_playback", **render_payload(body))

    @app.post("/autoplay/default/render/prepare")
    def render_prepare(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("prepare_default_render", **render_payload(body))

    @app.post("/autoplay/default/render/schedule")
    def render_schedule(body: dict[str, Any]) -> dict[str, Any]:
        return wrapped("schedule_default_render", **render_payload(body), min_lead_sec=float(body.get("min_lead_sec") or 1.5))

    @app.post("/autoplay/default/render/prepare-schedule")
    def render_prepare_schedule(body: dict[str, Any]) -> dict[str, Any]:
        payload = render_payload(body)
        prepared = runtime.command("prepare_default_render", **payload)
        result = runtime.command("schedule_default_render", **payload, min_lead_sec=float(body.get("min_lead_sec") or 1.5))
        return {"ok": True, "prepared": prepared, "result": result, "degraded": bool(result.get("degraded", False))}

    @app.post("/load_plan")
    async def load_plan(body: dict[str, Any]) -> dict[str, Any]:
        mix_plan = body.get("mix_plan") or {}
        manifest = body.get("manifest") or {}
        plan_path = config.state_root / "current-plan.json"
        plan_path.write_text(json.dumps({"mix_plan": mix_plan, "manifest": manifest}, ensure_ascii=True), encoding="utf-8")
        result = await runtime.command_async("load_plan", mix_plan=mix_plan)
        sync_started = False
        if manifest:
            response = await runtime.http_json("POST", "/sync", body={"manifest": manifest})
            sync_started = response.get("ok") is True
        return {"ok": True, "plan_id": mix_plan.get("plan_id"), "plan_path": str(plan_path), "sync_started": sync_started, "result": result}

    @app.post("/transition/validate")
    def validate(body: dict[str, Any]) -> dict[str, Any]:
        request = runtime.normalize(body)
        return {"ok": True, "request": request, "sync_request": build_priority_sync_request(request)}

    @app.post("/transition/tasks/accept")
    async def accept_compat(body: dict[str, Any]) -> dict[str, Any]:
        request = runtime.normalize(body)
        transition_id = request["transition_id"]
        try:
            task, reused = accept_or_reuse(
                request,
                protocol_tasks.get(transition_id),
                now=str(body.get("now") or "shadow"),
                deadline_epoch_sec=float(body.get("deadline_epoch_sec") or 1.0),
            )
        except OrchestrationValidationError as exc:
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
        protocol_tasks[transition_id] = task
        return {"reused": reused, "task": public_task(task, now_epoch_sec=time.time())}

    @app.post("/autoplay/default/render/orchestrate", status_code=202)
    async def orchestrate(body: dict[str, Any]) -> dict[str, Any]:
        task, _reused = await runtime.accept(body)
        return public_task(task, now_epoch_sec=time.time())

    @app.get("/autoplay/default/render/orchestrate/{transition_id}")
    async def get_orchestration(transition_id: str) -> dict[str, Any]:
        task = await runtime.reconcile_task(transition_id)
        if task is None:
            raise HTTPException(status_code=404, detail={"code": "transition_not_found"})
        return public_task(task, now_epoch_sec=time.time())

    @app.delete("/autoplay/default/render/orchestrate/{transition_id}")
    async def cancel_orchestration(transition_id: str) -> dict[str, Any]:
        task = runtime.tasks.get(transition_id)
        if task is None:
            raise HTTPException(status_code=404, detail={"code": "transition_not_found"})
        if task.get("state") in {"scheduled", "executed"}:
            raise HTTPException(status_code=409, detail={"code": "already_committed"})
        runner = runtime.runners.get(transition_id)
        if runner and not runner.done():
            runner.cancel()
            try:
                await runner
            except asyncio.CancelledError:
                pass
        task = runtime.tasks.get(transition_id) or task
        if task.get("state") != "cancelled":
            task = await runtime.set_task(transition_id, "cancelled")
        return public_task(task, now_epoch_sec=time.time())
