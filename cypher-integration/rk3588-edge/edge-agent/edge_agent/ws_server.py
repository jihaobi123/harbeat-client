"""WebSocket 服务 :9001 — 推送 P5 playback_state / P8 device_info。"""

from __future__ import annotations

import asyncio
import logging
import time

import websockets
from websockets.server import WebSocketServerProtocol

from .audio_client import AudioEngineError, audio_client
from .config import settings
from .state import edge_state

logger = logging.getLogger(__name__)


async def _ws_handler(ws: WebSocketServerProtocol) -> None:
  edge_state.register_ws(ws)
  logger.info("WS client connected: %s", ws.remote_address)
  try:
    async for _message in ws:
      # 骨架阶段：App 仅订阅，不处理入站命令
      pass
  finally:
    edge_state.unregister_ws(ws)
    logger.info("WS client disconnected: %s", ws.remote_address)


async def _playback_broadcast_loop() -> None:
  while True:
    try:
      state = audio_client.send_command({"cmd": "state"}, timeout=0.5)
      if state.get("ok") is not False:
        await edge_state.set_audio_ready(True)
        playback = await edge_state.replace_playback_from_audio(state)
      else:
        playback = await edge_state.snapshot_playback()
    except AudioEngineError:
      await edge_state.set_audio_ready(False)
      playback = await edge_state.snapshot_playback()
    await edge_state.broadcast(playback.model_dump())
    await asyncio.sleep(0.2)


async def _device_info_broadcast_loop() -> None:
  while True:
    jetson_reachable = None
    try:
      import httpx

      async with httpx.AsyncClient(timeout=1.0) as client:
        resp = await client.get(f"{settings.jetson_base_url.rstrip('/')}/health")
        jetson_reachable = resp.status_code < 500
    except Exception:
      jetson_reachable = False
    info = await edge_state.refresh_device_info(jetson_reachable=jetson_reachable)
    payload = info.model_dump()
    payload["ts"] = int(time.time() * 1000)
    await edge_state.broadcast(payload)
    await asyncio.sleep(5.0)


async def run_ws_server() -> None:
  async with websockets.serve(_ws_handler, settings.ws_host, settings.ws_port):
    logger.info("WebSocket listening on ws://%s:%s/ws", settings.ws_host, settings.ws_port)
    await asyncio.gather(
      _playback_broadcast_loop(),
      _device_info_broadcast_loop(),
    )


def main() -> None:
  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
  asyncio.run(run_ws_server())


if __name__ == "__main__":
  main()
