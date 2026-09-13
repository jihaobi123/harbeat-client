"""Wire protocol adapters for the RK audio-engine socket."""

from __future__ import annotations

import json
import math
import struct


def encode_audio_trigger(key: int, timestamp: float) -> bytes:
    """Encode one validated, length-prefixed audio trigger command."""
    if key < 0:
        raise ValueError("audio trigger key must be non-negative")
    if not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("timestamp must be a finite non-negative number")

    body = json.dumps(
        {"cmd": "trigger", "key": key, "ts": timestamp},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return struct.pack(">I", len(body)) + body
