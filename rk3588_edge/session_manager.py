"""Session manager — SessionEvent creation, buffering, and flush to Jetson backend.

SessionEvents track: load, play_started, play_paused, play_stopped,
crossfade_start, crossfade_end, key_press, trigger_fx, error.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import aiohttp

from .config import get_config

logger = logging.getLogger(__name__)


@dataclass
class SessionEvent:
    event_type: str          # load | play_started | play_paused | crossfade_start | ...
    session_id: str | None = None
    event_value: dict[str, Any] | None = None
    timestamp: float = field(default_factory=time.time)

    def to_api(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "event_value": json.dumps(self.event_value) if self.event_value else None,
            "created_at": self._iso_timestamp(),
        }

    def _iso_timestamp(self) -> str:
        import datetime
        return datetime.datetime.fromtimestamp(self.timestamp, tz=datetime.timezone.utc).isoformat()


class SessionManager:
    """Buffered session event recorder, flushes to Jetson backend periodically."""

    def __init__(self):
        self._config = get_config()
        self._events: list[SessionEvent] = []
        self._session_id: str | None = None
        self._flush_task: asyncio.Task | None = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self, session_id: str | None = None):
        self._session_id = session_id
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("session_manager started (session=%s)", self._session_id)

    async def stop(self):
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush()
        logger.info("session_manager stopped (%d events flushed)", len(self._events))

    # ── Event Recording ───────────────────────────────────────────────

    def record_sync(self, event_type: str, **value_kwargs):
        event = SessionEvent(
            event_type=event_type,
            session_id=self._session_id,
            event_value=value_kwargs if value_kwargs else None,
        )
        self._events.append(event)
        # Log significant events immediately
        if event_type in ("load", "play_started", "crossfade_start", "error"):
            logger.info("session_event: %s %s", event_type, value_kwargs)

    # ── Flush ─────────────────────────────────────────────────────────

    async def _flush_loop(self):
        while self._running:
            await asyncio.sleep(self._config.session_flush_interval_sec)
            await self._flush()

    async def _flush(self):
        if not self._events:
            return
        batch = self._events[:self._config.session_flush_batch_size]
        self._events = self._events[self._config.session_flush_batch_size:]

        try:
            url = f"{self._config.jetson_base_url}/sessions/events"
            payload = {"events": [e.to_api() for e in batch]}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status < 200 or resp.status >= 300:
                        text = await resp.text()
                        logger.warning("session flush HTTP %d: %s", resp.status, text[:200])
                        # Re-queue on failure
                        self._events = batch + self._events
                    else:
                        logger.debug("session flush: %d events OK", len(batch))
        except Exception as exc:
            logger.warning("session flush failed: %s (re-queuing %d events)", exc, len(batch))
            self._events = batch + self._events

    # ── Recovery ──────────────────────────────────────────────────────

    async def recover_plan(self, plan_id: str) -> dict[str, Any] | None:
        """Try to recover the current plan from Jetson on startup."""
        try:
            url = f"{self._config.jetson_base_url}/manifest/plan/{plan_id}/state"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None


# Singleton
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
