#!/usr/bin/env python3
"""同时启动 REST (:9000) 与 WebSocket (:9001)。"""

from __future__ import annotations

import asyncio
import logging

import uvicorn

from edge_agent.config import settings
from edge_agent.ws_server import run_ws_server


async def _run_rest() -> None:
  config = uvicorn.Config(
    "main:app",
    host=settings.rest_host,
    port=settings.rest_port,
    log_level="info",
    reload=False,
  )
  server = uvicorn.Server(config)
  await server.serve()


async def _main_async() -> None:
  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
  await asyncio.gather(_run_rest(), run_ws_server())


def main() -> None:
  asyncio.run(_main_async())


if __name__ == "__main__":
  main()
