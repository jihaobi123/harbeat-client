"""WebSocket 广播循环（App :9000/ws/control 与兼容 :9001/ws）。"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from .app_compat import build_app_device_info_ws, build_app_playback, build_sync_progress
from .audio_client import AudioEngineError, audio_client
from .config import settings
from .state import edge_state

logger = logging.getLogger(__name__)


async def playback_broadcast_loop() -> None:
  while True:
    try:
      state = audio_client.send_command({"cmd": "state"}, timeout=0.5)
      if state.get("ok") is not False:
        await edge_state.set_audio_ready(True)
        await edge_state.replace_playback_from_audio(state)
      else:
        await edge_state.set_audio_ready(False)
      pb = await edge_state.snapshot_playback()
      d = pb.model_dump()
      await edge_state.broadcast(
        {
          "type": "playback_state",
          "ts": d["ts"],
          "playing": d["playing"],
          "paused": d["paused"],
          "current_song_id": d["current_song_id"],
          "position_sec": d["position_sec"],
          "duration_sec": d.get("duration_sec") or 0.0,
          "bpm": d.get("bpm") or 120,
          "active_loops": d.get("active_loops") or [],
        }
      )
    except AudioEngineError:
      await edge_state.set_audio_ready(False)
    except Exception as exc:
      logger.debug("playback broadcast: %s", exc)
    await asyncio.sleep(0.2)


async def device_info_broadcast_loop() -> None:
  while True:
    try:
      jetson_reachable = None
      try:
        async with httpx.AsyncClient(timeout=1.0) as client:
          resp = await client.get(f"{settings.jetson_base_url.rstrip('/')}/health")
          jetson_reachable = resp.status_code < 500
      except Exception:
        jetson_reachable = False
      await edge_state.refresh_device_info(jetson_reachable=jetson_reachable)
      payload = await build_app_device_info_ws()
      await edge_state.broadcast(payload)
    except Exception as exc:
      logger.debug("device_info broadcast: %s", exc)
    await asyncio.sleep(5.0)


async def sync_progress_broadcast_loop() -> None:
  last_running = False
  while True:
    try:
      async with httpx.AsyncClient(timeout=1.0) as client:
        resp = await client.get(f"{settings.sync_worker_url.rstrip('/')}/status")
        if resp.status_code == 200:
          status = resp.json()
          msg = build_sync_progress(status)
          if msg and (status.get("running") or last_running):
            await edge_state.broadcast(msg)
          last_running = bool(status.get("running"))
    except Exception:
      pass
    await asyncio.sleep(1.0)


def start_background_tasks() -> list[asyncio.Task]:
  return [
    asyncio.create_task(playback_broadcast_loop()),
    asyncio.create_task(device_info_broadcast_loop()),
    asyncio.create_task(sync_progress_broadcast_loop()),
  ]
