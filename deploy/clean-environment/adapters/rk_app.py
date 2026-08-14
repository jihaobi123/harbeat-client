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
        from .edge_transport import install_edge_routes

        install_edge_routes(app, config, _audio_command)
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
    os.environ["CYPHER_HOME"] = str(config.asset_root)
    os.environ["JETSON_BASE_URL"] = str(config.settings["jetson_base_url"])
    module = importlib.import_module("harbeat_asset_sync.sync_worker")
    module.CYPHER_HOME = config.asset_root
    module.CACHE_DIR = config.asset_root / "cache"
    wrapper = FastAPI(title="HarBeat clean sync-worker", version="0.3.0")

    @wrapper.get("/health")
    async def health() -> dict[str, Any]:
        return _health_payload(config, sync_status=await module.state.snapshot())

    wrapper.mount("/", module.app)
    return wrapper


def _audio_engine_app(config: AdapterConfig) -> FastAPI:
    socket_path = str(config.settings["audio_socket"])
    os.environ["CYPHER_HOME"] = str(config.asset_root)
    if config.settings.get("audio_device"):
        os.environ["CYPHER_AUDIO_DEVICE"] = str(config.settings["audio_device"])
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
