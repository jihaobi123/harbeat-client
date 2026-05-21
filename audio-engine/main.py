#!/usr/bin/env python3
"""audio-engine MVP 入口。"""

from __future__ import annotations

import logging
import json
import signal
import sys
import time

from config import CYPHER_HOME
from engine import engine
from socket_server import AudioSocketServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("audio-engine")


def main() -> None:
    # 启动时预开声卡，避免首次 /play 在 socket 线程里阻塞过久
    try:
        engine._ensure_stream()
    except Exception as exc:
        logger.warning("output stream init failed (no audio device?): %s", exc)

    plan_path = CYPHER_HOME / "plans" / "current.json"
    if plan_path.exists():
        try:
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            mix_plan = payload.get("mix_plan") if isinstance(payload, dict) else None
            if isinstance(mix_plan, dict):
                engine.load_plan(mix_plan)
                logger.info("restored mix_plan from %s", plan_path)
        except Exception as exc:
            logger.warning("failed to restore mix_plan from %s: %s", plan_path, exc)

    server = AudioSocketServer()
    server.start()
    logger.info("audio-engine MVP ready")

    def _shutdown(signum, frame) -> None:
        logger.info("shutting down (signal %s)", signum)
        engine.shutdown()
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT, None)


if __name__ == "__main__":
    main()
