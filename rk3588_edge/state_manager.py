"""Playback state manager — single source of truth for RK3588 edge agent.

Holds in-memory playback state with playback_tier tracking and WebSocket
broadcast to connected App clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from fastapi import WebSocket

from .config import DeckSide, PlaybackTier, get_config

logger = logging.getLogger(__name__)


@dataclass
class DeckState:
    side: DeckSide
    song_id: str | None = None
    playing: bool = False
    position_sec: float = 0.0
    bpm: float | None = None
    stems_loaded: bool = False


@dataclass
class TransitionState:
    active: bool = False
    style: str = ""
    from_song_id: str | None = None
    to_song_id: str | None = None
    elapsed_sec: float = 0.0
    duration_sec: float = 0.0


@dataclass
class PlaybackState:
    tier: PlaybackTier = PlaybackTier.basic
    deck_a: DeckState = field(default_factory=lambda: DeckState(DeckSide.A))
    deck_b: DeckState = field(default_factory=lambda: DeckState(DeckSide.B))
    transition: TransitionState = field(default_factory=TransitionState)
    current_plan_id: str | None = None
    manifest_loaded: bool = False
    sync_complete: bool = False
    sync_errors: list[str] = field(default_factory=list)
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "deck_a": asdict(self.deck_a),
            "deck_b": asdict(self.deck_b),
            "transition": asdict(self.transition),
            "current_plan_id": self.current_plan_id,
            "manifest_loaded": self.manifest_loaded,
            "sync_complete": self.sync_complete,
            "sync_errors": self.sync_errors[-10:],  # Last 10 errors
            "updated_at": self.updated_at,
        }


class StateManager:
    """Thread-safe state holder with WebSocket fan-out."""

    def __init__(self):
        self._state = PlaybackState()
        self._lock = asyncio.Lock()
        self._ws_clients: set[WebSocket] = set()
        self._config = get_config()

    # ── Read ──────────────────────────────────────────────────────────

    async def get_state(self) -> dict[str, Any]:
        async with self._lock:
            return self._state.to_dict()

    async def get_tier(self) -> PlaybackTier:
        async with self._lock:
            return self._state.tier

    # ── Write ─────────────────────────────────────────────────────────

    async def set_tier(self, tier: PlaybackTier):
        async with self._lock:
            old = self._state.tier
            self._state.tier = tier
            self._state.updated_at = time.time()
            if old != tier:
                logger.info("playback_tier: %s → %s", old.value, tier.value)
        await self._broadcast()

    async def update_deck(self, side: DeckSide, **kwargs):
        async with self._lock:
            deck = self._state.deck_a if side == DeckSide.A else self._state.deck_b
            for k, v in kwargs.items():
                if hasattr(deck, k):
                    setattr(deck, k, v)
            # Auto-detect tier from stems
            if self._state.deck_a.stems_loaded and self._state.deck_b.stems_loaded:
                new_tier = PlaybackTier.stem_aware
            elif self._state.deck_a.playing or self._state.deck_b.playing:
                new_tier = PlaybackTier.non_stem
            else:
                new_tier = PlaybackTier.basic
            if self._state.tier != new_tier:
                self._state.tier = new_tier
                logger.info("playback_tier auto → %s", new_tier.value)
            self._state.updated_at = time.time()
        await self._broadcast()

    async def update_transition(self, **kwargs):
        async with self._lock:
            t = self._state.transition
            for k, v in kwargs.items():
                if hasattr(t, k):
                    setattr(t, k, v)
            self._state.updated_at = time.time()
        await self._broadcast()

    async def set_plan(self, plan_id: str):
        async with self._lock:
            self._state.current_plan_id = plan_id
            self._state.manifest_loaded = False
            self._state.sync_complete = False
            self._state.sync_errors.clear()
            self._state.updated_at = time.time()
        await self._broadcast()

    async def set_sync_complete(self, success: bool, errors: list[str] | None = None):
        async with self._lock:
            self._state.sync_complete = success
            self._state.manifest_loaded = success
            if errors:
                self._state.sync_errors.extend(errors)
            self._state.updated_at = time.time()
        await self._broadcast()

    async def add_sync_error(self, error: str):
        async with self._lock:
            self._state.sync_errors.append(error)
            self._state.updated_at = time.time()
        await self._broadcast()

    # ── WebSocket ─────────────────────────────────────────────────────

    async def register_ws(self, ws: WebSocket):
        self._ws_clients.add(ws)
        logger.debug("WS client connected (total=%d)", len(self._ws_clients))

    async def unregister_ws(self, ws: WebSocket):
        self._ws_clients.discard(ws)
        logger.debug("WS client disconnected (total=%d)", len(self._ws_clients))

    async def _broadcast(self):
        if not self._ws_clients:
            return
        state_dict = await self.get_state()
        payload = json.dumps({"type": "playback_state", "data": state_dict})
        dead: list[WebSocket] = []
        for ws in self._ws_clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)


# Singleton
_state_manager: StateManager | None = None


def get_state_manager() -> StateManager:
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager
