"""向 audio-engine 发送 trigger（fire-and-forget，低延迟）。"""

from __future__ import annotations

import json
import socket
import struct
from typing import Any

from config import AUDIO_SOCKET


def send_trigger(key: int, ts: float) -> None:
    payload = {"cmd": "trigger", "key": key, "ts": ts}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    frame = struct.pack(">I", len(body)) + body
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        sock.connect(AUDIO_SOCKET)
        sock.sendall(frame)
        # 不等待响应，减少按键延迟


def send_command(payload: dict[str, Any], timeout: float = 0.5) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    frame = struct.pack(">I", len(body)) + body
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(AUDIO_SOCKET)
        sock.sendall(frame)
        header = sock.recv(4)
        if len(header) < 4:
            return {}
        length = struct.unpack(">I", header)[0]
        if length == 0:
            return {}
        return json.loads(sock.recv(length).decode("utf-8"))
