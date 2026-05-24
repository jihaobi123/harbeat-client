"""Audio engine interface — sends commands to the real RK3588 audio engine.

Communicates via Unix domain socket (JSON-line protocol).
The real engine handles: deck load, play, pause, stop, crossfade, trigger FX.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from .config import DeckSide, get_config
from .session_manager import SessionManager, get_session_manager
from .state_manager import StateManager, get_state_manager

logger = logging.getLogger(__name__)


class AudioEngineError(Exception):
    pass


class AudioEngine:
    """Async stub for the real RK3588 audio engine process."""

    def __init__(self):
        self._config = get_config()
        self._state: StateManager = get_state_manager()
        self._session: SessionManager = get_session_manager()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._connected = False

    # ── Connection ────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Connect to the audio engine Unix socket."""
        sock_path = self._config.audio_engine_socket
        if not os.path.exists(sock_path):
            logger.warning("audio engine socket not found: %s", sock_path)
            return False
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(sock_path),
                timeout=5.0,
            )
            self._reader = reader
            self._writer = writer
            self._connected = True
            logger.info("audio engine connected: %s", sock_path)
            return True
        except Exception as exc:
            logger.warning("audio engine connection failed: %s", exc)
            return False

    async def disconnect(self):
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        self._connected = False

    # ── Commands ──────────────────────────────────────────────────────

    async def _send(self, cmd: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            if not self._connected or not self._writer:
                raise AudioEngineError("not connected to audio engine")
            payload = json.dumps(cmd) + "\n"
            self._writer.write(payload.encode())
            await self._writer.drain()

            if not self._reader:
                raise AudioEngineError("reader lost")
            line = await asyncio.wait_for(self._reader.readline(), timeout=10.0)
            return json.loads(line.decode())

    async def health(self) -> dict[str, Any]:
        try:
            return await self._send({"cmd": "health"})
        except Exception:
            return {"ok": False, "error": "audio engine unreachable"}

    async def load_deck(self, side: DeckSide, song_id: str, file_path: str,
                        stems: dict[str, str] | None = None) -> dict[str, Any]:
        cmd: dict[str, Any] = {
            "cmd": "load",
            "deck": side.value,
            "song_id": song_id,
            "file": file_path,
        }
        if stems:
            cmd["stems"] = stems

        try:
            result = await self._send(cmd)
        except Exception as exc:
            raise AudioEngineError(f"load failed: {exc}")

        ok = result.get("ok", False)
        if ok:
            await self._state.update_deck(
                side, song_id=song_id, stems_loaded=bool(stems),
                playing=False, position_sec=0.0,
            )
            await self._session.record("load", deck=side.value, song_id=song_id, ok=True)
        else:
            await self._session.record("error", action="load", deck=side.value,
                                       song_id=song_id, error=result.get("error", "unknown"))
        return result

    async def play(self, side: DeckSide, start_sec: float = 0.0) -> dict[str, Any]:
        try:
            result = await self._send({"cmd": "play", "deck": side.value, "start_sec": start_sec})
        except Exception as exc:
            raise AudioEngineError(f"play failed: {exc}")

        if result.get("ok"):
            await self._state.update_deck(side, playing=True)
            await self._session.record("play_started", deck=side.value, start_sec=start_sec)
        return result

    async def pause(self, side: DeckSide) -> dict[str, Any]:
        result = await self._send({"cmd": "pause", "deck": side.value})
        if result.get("ok"):
            await self._state.update_deck(side, playing=False)
            await self._session.record("play_paused", deck=side.value)
        return result

    async def stop(self, side: DeckSide) -> dict[str, Any]:
        result = await self._send({"cmd": "stop", "deck": side.value})
        if result.get("ok"):
            await self._state.update_deck(side, playing=False, position_sec=0.0)
            await self._session.record("play_stopped", deck=side.value)
        return result

    async def crossfade(self, style: str, duration_sec: float,
                        from_deck: DeckSide, to_deck: DeckSide) -> dict[str, Any]:
        cmd = {
            "cmd": "xfade",
            "style": style,
            "duration_sec": duration_sec,
            "from": from_deck.value,
            "to": to_deck.value,
        }
        try:
            result = await self._send(cmd)
        except Exception as exc:
            raise AudioEngineError(f"crossfade failed: {exc}")

        if result.get("ok"):
            await self._state.update_transition(
                active=True, style=style,
                from_song_id=None, to_song_id=None,
                duration_sec=duration_sec,
            )
            await self._session.record("crossfade_start", style=style,
                                       from_deck=from_deck.value, to_deck=to_deck.value)
        return result

    async def trigger(self, fx_id: int, side: DeckSide) -> dict[str, Any]:
        """Trigger a stem FX: 7/8/9 = stem-aware effects (bass kill, vocal mute, drum solo)."""
        result = await self._send({"cmd": "trigger", "fx_id": fx_id, "deck": side.value})
        await self._session.record("key_press", fx_id=fx_id, deck=side.value)
        return result

    async def state(self) -> dict[str, Any]:
        """Get raw state from audio engine."""
        try:
            return await self._send({"cmd": "state"})
        except Exception:
            return {"ok": False, "error": "audio engine unreachable"}


# Singleton
_audio_engine: AudioEngine | None = None


def get_audio_engine() -> AudioEngine:
    global _audio_engine
    if _audio_engine is None:
        _audio_engine = AudioEngine()
    return _audio_engine


def get_session_manager() -> SessionManager:
    """Session manager singleton (same module for co-location)."""
    from .session_manager import SessionManager as SM
    _sm: SM | None = getattr(get_session_manager, "_instance", None)
    if _sm is None:
        _sm = SM()
        setattr(get_session_manager, "_instance", _sm)
    return _sm
