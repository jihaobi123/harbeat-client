"""通过 Unix socket 向 audio-engine 转发命令。"""

from __future__ import annotations

import json
import logging
import socket
import struct
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

_SOCK_TIMEOUT_SEC = 5.0


class AudioEngineError(Exception):
  """audio-engine 通信失败。"""


class AudioEngineClient:
  """长度前缀（4 字节 big-endian uint32）+ JSON 协议。"""

  def __init__(self, socket_path: str | None = None) -> None:
    self.socket_path = socket_path or settings.audio_socket

  def is_reachable(self) -> bool:
    try:
      self.send_command({"cmd": "ping"}, timeout=0.5)
      return True
    except AudioEngineError:
      return False

  def send_command(self, payload: dict[str, Any], timeout: float = _SOCK_TIMEOUT_SEC) -> dict[str, Any]:
    message = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    frame = struct.pack(">I", len(message)) + message

    try:
      with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(self.socket_path)
        sock.sendall(frame)

        header = self._recv_exact(sock, 4, timeout)
        if not header:
          return {"ok": True, "note": "no response body"}
        length = struct.unpack(">I", header)[0]
        if length == 0:
          return {"ok": True}
        body = self._recv_exact(sock, length, timeout)
        if not body:
          return {"ok": True}
        return json.loads(body.decode("utf-8"))
    except FileNotFoundError as exc:
      raise AudioEngineError(f"audio socket 不存在: {self.socket_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
      raise AudioEngineError(str(exc)) from exc

  @staticmethod
  def _recv_exact(sock: socket.socket, size: int, timeout: float) -> bytes:
    sock.settimeout(timeout)
    chunks: list[bytes] = []
    received = 0
    while received < size:
      chunk = sock.recv(size - received)
      if not chunk:
        break
      chunks.append(chunk)
      received += len(chunk)
    return b"".join(chunks)


audio_client = AudioEngineClient()
