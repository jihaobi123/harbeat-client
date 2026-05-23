"""Unix socket 服务：4 字节 big-endian 长度 + JSON。"""

from __future__ import annotations

import json
import logging
import os
import socket
import struct
import threading
from typing import Any

from config import AUDIO_SOCKET
from engine import AudioEngineMVP, SongCacheError, engine

logger = logging.getLogger(__name__)


def _send_response(conn: socket.socket, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    conn.sendall(struct.pack(">I", len(body)) + body)


def _recv_frame(conn: socket.socket) -> dict[str, Any] | None:
    header = _recv_exact(conn, 4)
    if not header:
        return None
    length = struct.unpack(">I", header)[0]
    if length == 0:
        return {}
    body = _recv_exact(conn, length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while received < size:
        chunk = conn.recv(size - received)
        if not chunk:
            break
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def _handle_command(msg: dict[str, Any]) -> dict[str, Any]:
    cmd = msg.get("cmd")
    if cmd == "ping":
        return {"ok": True, "pong": True, **engine.get_state()}
    if cmd == "state":
        return {"ok": True, **engine.get_state()}
    if cmd == "play":
        result = engine.play(msg["song_id"], float(msg.get("start_at_sec", 0)))
        return {"ok": True, **result}
    if cmd == "pause":
        return {"ok": True, **engine.pause()}
    if cmd == "resume":
        return {"ok": True, **engine.resume()}
    if cmd == "seek":
        return {"ok": True, **engine.seek(float(msg["sec"]))}
    if cmd == "next":
        return {"ok": True, **engine.next_track()}
    if cmd == "xfade":
        result = engine.manual_transition(
            msg["to_song_id"],
            fade_sec=float(msg.get("fade_sec", 4.0)),
            to_at_sec=float(msg.get("to_at_sec", 0.0)),
            style=str(msg.get("style", "smooth") or "smooth"),
        )
        return {"ok": True, **result}
    if cmd == "stem_solo":
        stem = msg.get("stem")
        if stem in ("", "null", "none"):
            stem = None
        result = engine.set_stem_solo(stem)
        return {"ok": True, **result}
    if cmd == "prefetch":
        raw = msg.get("song_ids") or ([msg["song_id"]] if "song_id" in msg else [])
        result = engine.prefetch(list(raw))
        return {"ok": True, **result}
    if cmd == "trigger":
        return {"ok": True, **engine.trigger(int(msg["key"]))}
    if cmd == "set_deck_eq":
        result = engine.set_deck_eq(
            str(msg.get("deck", "active")),
            float(msg.get("low_db", 0.0)),
            float(msg.get("mid_db", 0.0)),
            float(msg.get("hi_db", 0.0)),
        )
        return {"ok": bool(result.get("ok", True)), **result}
    if cmd == "load_plan":
        engine.load_plan(msg.get("mix_plan") or {})
        return {"ok": True, "plan_id": (msg.get("mix_plan") or {}).get("plan_id")}
    if cmd == "stop":
        engine.stop()
        return {"ok": True}
    return {"ok": False, "error": f"unknown cmd: {cmd}", "code": 400}


def _client_handler(conn: socket.socket) -> None:
    try:
        while True:
            msg = _recv_frame(conn)
            if msg is None:
                break
            try:
                result = _handle_command(msg)
            except SongCacheError as exc:
                result = {"ok": False, "error": str(exc), "code": exc.code}
            except Exception as exc:
                logger.exception("command failed: %s", msg)
                result = {"ok": False, "error": str(exc), "code": 500}
            _send_response(conn, result)
    finally:
        conn.close()


class AudioSocketServer:
    def __init__(self, socket_path: str = AUDIO_SOCKET) -> None:
        self.socket_path = socket_path
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.socket_path)
        os.chmod(self.socket_path, 0o666)
        self._server.listen(8)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="audio-socket")
        self._thread.start()
        logger.info("listening on %s", self.socket_path)

    def _accept_loop(self) -> None:
        assert self._server is not None
        while self._running:
            try:
                conn, _ = self._server.accept()
            except OSError:
                break
            threading.Thread(
                target=_client_handler,
                args=(conn,),
                daemon=True,
                name="audio-client",
            ).start()

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
