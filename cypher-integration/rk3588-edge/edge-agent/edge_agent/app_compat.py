"""HarBeat App API 兼容：响应格式、状态映射、鉴权。"""

from __future__ import annotations

import socket
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import Header, HTTPException

from .config import settings
from .pairing import pairing_store
from .state import edge_state


def app_success(message: str, **extra: Any) -> dict[str, Any]:
  body: dict[str, Any] = {"success": True, "message": message}
  body.update(extra)
  return body


def app_fail(message: str, error_code: str = "ERROR") -> dict[str, Any]:
  return {"success": False, "message": message, "error_code": error_code}


def local_base_url() -> str:
  if settings.public_base_url:
    return settings.public_base_url.rstrip("/")
  host = settings.rest_host
  if host in ("0.0.0.0", "::"):
    try:
      s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      s.connect(("8.8.8.8", 80))
      host = s.getsockname()[0]
      s.close()
    except OSError:
      host = "127.0.0.1"
  return f"http://{host}:{settings.rest_port}"


async def build_edge_info() -> dict[str, Any]:
  info = await edge_state.refresh_device_info()
  return {
    "device_id": settings.rk_id,
    "model": settings.device_model,
    "status": "connected" if edge_state.audio_ready else "disconnected",
    "battery": 100,
    "cpu_pct": info.cpu_percent,
    "mem_mb": int(info.mem_used_mb),
    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
  }


async def build_app_playback() -> dict[str, Any]:
  try:
    from edge_agent.audio_client import audio_client, AudioEngineError

    state = audio_client.send_command({"cmd": "state"}, timeout=1.0)
    if state.get("ok") is not False:
      await edge_state.set_audio_ready(True)
      pb = await edge_state.replace_playback_from_audio(state)
    else:
      pb = await edge_state.snapshot_playback()
  except Exception:
    pb = await edge_state.snapshot_playback()

  d = pb.model_dump()
  return {
    "type": "playback_state",
    "ts": d["ts"],
    "playing": d["playing"],
    "paused": d["paused"],
    "current_song_id": d["current_song_id"],
    "position_sec": d["position_sec"],
    "duration_sec": d.get("duration_sec") or 0.0,
    "bpm": d.get("bpm") or 120,
    "active_loops": d.get("active_loops") or [],
    "next_song_id": d.get("next_song_id"),
    "next_transition_in_sec": d.get("next_transition_in_sec"),
    "active_stem_fx": d.get("active_stem_fx"),
  }


async def build_app_device_info_ws() -> dict[str, Any]:
  info = await edge_state.refresh_device_info()
  return {
    "type": "device_info",
    "ts": int(time.time() * 1000),
    "device_id": settings.rk_id,
    "model": settings.device_model,
    "status": "connected" if edge_state.audio_ready else "disconnected",
    "battery": 100,
    "cpu_pct": info.cpu_percent,
    "mem_mb": int(info.mem_used_mb),
    "jetson_reachable": info.jetson_reachable,
    "wifi_ssid": info.wifi_ssid,
  }


def build_sync_progress(sync_status: dict[str, Any] | None) -> dict[str, Any] | None:
  if not sync_status:
    return None
  return {
    "type": "sync_progress",
    "ts": int(time.time() * 1000),
    "running": sync_status.get("running", False),
    "percent": sync_status.get("percent", 0.0),
    "downloaded": sync_status.get("downloaded", 0),
    "total": sync_status.get("total", 0),
    "current_file": sync_status.get("current_file"),
    "errors": sync_status.get("errors", []),
  }


async def optional_app_auth(
  authorization: str | None = Header(default=None),
  x_edge_token: str | None = Header(default=None),
) -> None:
  """Bearer device_token、X-Edge-Token，或未启用鉴权时放行。"""
  if settings.edge_token and x_edge_token == settings.edge_token:
    return
  if authorization and authorization.lower().startswith("bearer "):
    token = authorization[7:].strip()
    if pairing_store.validate_token(token):
      return
  if settings.require_device_token:
    raise HTTPException(status_code=401, detail="invalid or missing device token")
  if settings.edge_token:
    raise HTTPException(status_code=401, detail="invalid edge token")
