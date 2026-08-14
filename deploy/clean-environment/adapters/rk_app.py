from __future__ import annotations

import dataclasses
import importlib
import json
import os
import socket
import struct
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException

from .config import AdapterConfig, RK_SERVICES


def create_rk_app(config: AdapterConfig) -> FastAPI:
    if config.service not in RK_SERVICES:
        raise ValueError(f"not an RK service: {config.service}")
    config.prepare_shadow_directories()
    if config.service == "sync-worker":
        return _sync_worker_app(config)
    if config.service == "audio-engine":
        return _audio_engine_app(config)

    app = FastAPI(title=f"HarBeat clean {config.service}", version="0.3.0")
    _health_route(app, config)
    if config.service == "edge-agent":
        _edge_routes(app, config)
    elif config.service == "input-daemon":
        _input_routes(app)
    return app


def _health_payload(config: AdapterConfig, **extra: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "service": config.service,
        "profile": config.profile,
        "mode": config.mode,
        "release": "0.3.0",
        "production_ready": False,
        **extra,
    }


def _health_route(app: FastAPI, config: AdapterConfig) -> None:
    @app.get("/health")
    def health() -> dict[str, Any]:
        return _health_payload(config)


def _sync_worker_app(config: AdapterConfig) -> FastAPI:
    os.environ["CYPHER_HOME"] = str(config.state_root)
    os.environ["JETSON_BASE_URL"] = str(config.settings["jetson_base_url"])
    module = importlib.import_module("harbeat_asset_sync.sync_worker")
    module.CYPHER_HOME = config.state_root
    module.CACHE_DIR = config.state_root / "cache"
    wrapper = FastAPI(title="HarBeat clean sync-worker", version="0.3.0")

    @wrapper.get("/health")
    async def health() -> dict[str, Any]:
        return _health_payload(config, sync_status=await module.state.snapshot())

    wrapper.mount("/", module.app)
    return wrapper


def _audio_engine_app(config: AdapterConfig) -> FastAPI:
    socket_path = str(config.settings["audio_socket"])
    from harbeat_audio_runtime.socket_server import AudioSocketServer

    server = AudioSocketServer(socket_path=socket_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        server.start()
        try:
            yield
        finally:
            server.stop()

    app = FastAPI(title="HarBeat clean audio-engine", version="0.3.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, Any]:
        response = _audio_command(socket_path, {"cmd": "ping"})
        return _health_payload(config, audio_socket=socket_path, audio_ready=response.get("ok") is True)

    return app


def _edge_routes(app: FastAPI, config: AdapterConfig) -> None:
    from harbeat_transition_orchestrator import (
        OrchestrationValidationError,
        accept_or_reuse,
        build_priority_sync_request,
        public_task,
        validate_request,
    )

    tasks: dict[str, dict[str, Any]] = {}

    def normalize(body: dict[str, Any]) -> dict[str, Any]:
        try:
            return validate_request(
                transition_id=str(body.get("transition_id") or ""),
                trigger=str(body.get("trigger") or ""),
                from_song_id=body.get("from_song_id"),
                to_song_id=body.get("to_song_id"),
                transition_plan=body.get("transition_plan") or {},
                pair_manifest=body.get("pair_manifest") or {},
                mode=str(body.get("mode") or "schedule"),
                min_lead_sec=float(body.get("min_lead_sec") or 1.5),
            )
        except (OrchestrationValidationError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/transition/validate")
    def validate(body: dict[str, Any]) -> dict[str, Any]:
        request = normalize(body)
        return {"ok": True, "request": request, "sync_request": build_priority_sync_request(request)}

    @app.post("/transition/tasks/accept")
    def accept(body: dict[str, Any]) -> dict[str, Any]:
        request = normalize(body)
        transition_id = request["transition_id"]
        try:
            task, reused = accept_or_reuse(
                request,
                tasks.get(transition_id),
                now=str(body.get("now") or "shadow"),
                deadline_epoch_sec=float(body.get("deadline_epoch_sec") or 1.0),
            )
        except OrchestrationValidationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        tasks[transition_id] = task
        return {"reused": reused, "task": public_task(task)}

    @app.get("/runtime/state")
    def runtime_state() -> dict[str, Any]:
        return _runtime_audio_command(config, {"cmd": "state"})

    @app.post("/runtime/play")
    def runtime_play(body: dict[str, Any]) -> dict[str, Any]:
        if body.get("song_id") in (None, ""):
            raise HTTPException(status_code=422, detail="song_id is required")
        return _runtime_audio_command(config, {
            "cmd": "play",
            "song_id": body["song_id"],
            "start_at_sec": body.get("start_at_sec", 0.0),
            "load_stems": body.get("load_stems", True),
        })

    @app.post("/runtime/pause")
    def runtime_pause() -> dict[str, Any]:
        return _runtime_audio_command(config, {"cmd": "pause"})

    @app.post("/runtime/resume")
    def runtime_resume() -> dict[str, Any]:
        return _runtime_audio_command(config, {"cmd": "resume"})

    @app.post("/runtime/seek")
    def runtime_seek(body: dict[str, Any]) -> dict[str, Any]:
        if body.get("sec") in (None, ""):
            raise HTTPException(status_code=422, detail="sec is required")
        return _runtime_audio_command(config, {"cmd": "seek", "sec": body["sec"]})

    @app.post("/runtime/default-render")
    def runtime_default_render(body: dict[str, Any]) -> dict[str, Any]:
        command = str(body.get("command") or "")
        if command not in {"prepare_default_render", "schedule_default_render", "default_render_playback"}:
            raise HTTPException(status_code=422, detail="unsupported default render command")
        return _runtime_audio_command(config, {
            "cmd": command,
            "transition_plan": body.get("transition_plan") or {},
            "to_song_id": body.get("to_song_id"),
            "render_path": body.get("render_path"),
            "min_lead_sec": body.get("min_lead_sec", 1.5),
        })


def _runtime_audio_command(config: AdapterConfig, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        result = _audio_command(str(config.settings["audio_socket"]), payload)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail=f"audio runtime unavailable: {exc}") from exc
    if result.get("ok") is False:
        raise HTTPException(status_code=int(result.get("code") or 502), detail=result.get("error") or "audio runtime command failed")
    return result


def _input_routes(app: FastAPI) -> None:
    from harbeat_physical_input import encode_audio_trigger, route_logical_key

    @app.post("/input/route")
    def route(body: dict[str, Any]) -> dict[str, Any]:
        try:
            key = int(body.get("key"))
            timestamp = float(body.get("timestamp") or 0.0)
            action = route_logical_key(key)
            response = dataclasses.asdict(action)
            response["kind"] = action.kind.value
            if action.audio_trigger_key is not None:
                response["audio_frame_bytes"] = len(encode_audio_trigger(action.audio_trigger_key, timestamp))
            return response
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


def _audio_command(socket_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2.0)
        client.connect(socket_path)
        client.sendall(struct.pack(">I", len(body)) + body)
        header = _recv_exact(client, 4)
        size = struct.unpack(">I", header)[0]
        return json.loads(_recv_exact(client, size).decode("utf-8"))


def _recv_exact(client: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    while sum(map(len, chunks)) < size:
        chunk = client.recv(size - sum(map(len, chunks)))
        if not chunk:
            raise RuntimeError("audio socket closed early")
        chunks.append(chunk)
    return b"".join(chunks)
