"""Map normalized physical keys to side-effect-free action descriptions."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass

SFX_KEYS = frozenset({1, 2, 3, 4, 5})
NAVIGATION_KEYS = frozenset({7, 8, 9})
PAUSE_KEY = 0
VINYL_STOP_PHYSICAL_KEY = 6
VINYL_STOP_SAMPLE_KEY = 3
VOLUME_UP_KEY = 100
VOLUME_DOWN_KEY = 101


@dataclass(frozen=True)
class InputAction:
    logical_key: int
    audio_trigger_key: int | None = None
    volume_direction: str | None = None
    notify_edge: bool = True

    @property
    def kind(self) -> str:
        if self.audio_trigger_key is not None:
            return "audio_trigger"
        if self.volume_direction is not None:
            return "volume"
        return "navigation_event"


def route_logical_key(key: int) -> InputAction:
    """Return the deployed action for one normalized MYKB logical key."""
    if key in SFX_KEYS:
        return InputAction(logical_key=key, audio_trigger_key=key)
    if key == VINYL_STOP_PHYSICAL_KEY:
        return InputAction(logical_key=key, audio_trigger_key=VINYL_STOP_SAMPLE_KEY)
    if key == PAUSE_KEY:
        return InputAction(logical_key=key, audio_trigger_key=PAUSE_KEY)
    if key == VOLUME_UP_KEY:
        return InputAction(logical_key=key, volume_direction="+")
    if key == VOLUME_DOWN_KEY:
        return InputAction(logical_key=key, volume_direction="-")
    if key in NAVIGATION_KEYS:
        return InputAction(logical_key=key)
    raise ValueError(f"unsupported logical key: {key}")


def encode_audio_trigger(key: int, timestamp: float) -> bytes:
    """Encode the deployed four-byte-length-prefixed audio socket command."""
    body = json.dumps(
        {"cmd": "trigger", "key": key, "ts": timestamp},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return struct.pack(">I", len(body)) + body
