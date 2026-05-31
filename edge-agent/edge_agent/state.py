"""edge-agent 与 WS 共享的运行时状态。"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings
from .models import DeviceInfo, KeyEvent, RKPlaybackState


class EdgeState:
  def __init__(self) -> None:
    self._lock = asyncio.Lock()
    self.audio_ready = False
    self.current_song_id: int | str | None = None
    self.plan_id: str | None = None
    self.session_id = ""
    self.playback = RKPlaybackState(ts=int(time.time() * 1000))
    self.device_info = DeviceInfo(ts=int(time.time() * 1000))
    self._ws_clients: set[Any] = set()
    self.event_buffer: list[dict[str, Any]] = []
    self._last_cpu: tuple[int, int] | None = None
    self._last_in_transition = False
    self._last_current_song_id: int | str | None = None

  def init_runtime(self) -> str:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    if settings.session_id_path.exists():
      sid = settings.session_id_path.read_text(encoding="utf-8").strip()
    else:
      sid = uuid.uuid4().hex
      settings.session_id_path.write_text(sid + "\n", encoding="utf-8")
    self.session_id = sid
    self._load_persisted_events()
    return sid

  async def start_new_session(self) -> str:
    sid = uuid.uuid4().hex
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.session_id_path.write_text(sid + "\n", encoding="utf-8")
    async with self._lock:
      self.session_id = sid
    return sid

  async def update_playback(self, **kwargs: Any) -> None:
    async with self._lock:
      data = self.playback.model_dump()
      data.update(kwargs)
      data["ts"] = int(time.time() * 1000)
      self.playback = RKPlaybackState(**data)
      if "current_song_id" in kwargs:
        self.current_song_id = kwargs["current_song_id"]

  async def set_audio_ready(self, ready: bool) -> None:
    async with self._lock:
      self.audio_ready = ready

  async def set_plan_id(self, plan_id: str | None) -> None:
    async with self._lock:
      self.plan_id = plan_id

  async def append_event(self, event: dict[str, Any]) -> None:
    normalized = self._normalize_event(event)
    async with self._lock:
      self.event_buffer.append(normalized)

  async def snapshot_playback(self) -> RKPlaybackState:
    async with self._lock:
      return self.playback.model_copy(deep=True)

  async def replace_playback_from_audio(self, state: dict[str, Any]) -> RKPlaybackState:
    """Merge the audio-engine state response into the public playback model."""
    data = self.playback.model_dump()
    for key in (
      "playing",
      "paused",
      "current_song_id",
      "position_sec",
      "duration_sec",
      "next_song_id",
      "next_transition_in_sec",
      "active_loops",
      "active_stem_fx",
    ):
      if key in state:
        data[key] = state[key]
    if "audio_xrun_count" in state:
      self.device_info.audio_xrun_count = int(state.get("audio_xrun_count") or 0)
    data["ts"] = int(time.time() * 1000)
    playback = RKPlaybackState(**data)
    async with self._lock:
      in_transition = bool(state.get("in_transition"))
      if in_transition and not self._last_in_transition:
        self.event_buffer.append(
          self._normalize_event(
            {
              "type": "crossfade_start",
              "from": self._last_current_song_id,
              "to": playback.next_song_id,
            }
          )
        )
      if not in_transition and self._last_in_transition:
        self.event_buffer.append(
          self._normalize_event(
            {
              "type": "crossfade_end",
              "current_song_id": playback.current_song_id,
            }
          )
        )
      self._last_in_transition = in_transition
      self._last_current_song_id = playback.current_song_id
      self.playback = playback
      self.current_song_id = playback.current_song_id
      return playback.model_copy(deep=True)

  async def snapshot_device_info(self) -> DeviceInfo:
    await self.refresh_device_info()
    async with self._lock:
      return self.device_info.model_copy(deep=True)

  async def refresh_device_info(self, jetson_reachable: bool | None = None) -> DeviceInfo:
    data = self.device_info.model_dump()
    data["ts"] = int(time.time() * 1000)
    data["cpu_percent"] = self._cpu_percent()
    data["mem_used_mb"] = self._mem_used_mb()
    data["temp_c"] = self._temp_c()
    try:
      data["disk_free_gb"] = round(shutil.disk_usage(settings.cypher_home).free / (1024**3), 2)
    except OSError:
      data["disk_free_gb"] = 0.0
    if jetson_reachable is not None:
      data["jetson_reachable"] = jetson_reachable
    data["wifi_ssid"] = self._wifi_ssid()
    info = DeviceInfo(**data)
    async with self._lock:
      self.device_info = info
      return info.model_copy(deep=True)

  def register_ws(self, ws: Any) -> None:
    self._ws_clients.add(ws)

  def unregister_ws(self, ws: Any) -> None:
    self._ws_clients.discard(ws)

  async def broadcast(self, message: dict[str, Any]) -> None:
    dead: list[Any] = []
    text = json.dumps(message, ensure_ascii=False)
    for ws in list(self._ws_clients):
      try:
        await ws.send(text)
      except Exception:
        dead.append(ws)
    for ws in dead:
      self.unregister_ws(ws)

  async def push_key_event(self, key: int, source: str = "app") -> None:
    evt = KeyEvent(ts=int(time.time() * 1000), key=key, source=source)  # type: ignore[arg-type]
    await self.append_event({"type": "key_press", "key": key, "source": source})
    await self.broadcast(evt.model_dump())

  def save_current_plan(self, mix_plan: dict[str, Any], manifest: dict[str, Any]) -> Path:
    settings.plans_dir.mkdir(parents=True, exist_ok=True)
    payload = {"mix_plan": mix_plan, "manifest": manifest}
    settings.current_plan_path.write_text(
      json.dumps(payload, ensure_ascii=False, indent=2),
      encoding="utf-8",
    )
    return settings.current_plan_path

  def load_current_plan(self) -> dict[str, Any] | None:
    path = settings.current_plan_path
    if not path.exists():
      return None
    return json.loads(path.read_text(encoding="utf-8"))

  async def pop_event_batch(self, limit: int) -> list[dict[str, Any]]:
    async with self._lock:
      batch = self.event_buffer[:limit]
      self.event_buffer = self.event_buffer[limit:]
      return batch

  async def restore_event_batch_front(self, batch: list[dict[str, Any]]) -> None:
    if not batch:
      return
    async with self._lock:
      self.event_buffer = batch + self.event_buffer

  def persist_events(self, events: list[dict[str, Any]]) -> None:
    if not events:
      return
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    with settings.event_buffer_path.open("w", encoding="utf-8") as f:
      for event in events:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

  def _load_persisted_events(self) -> None:
    path = settings.event_buffer_path
    if not path.exists():
      return
    loaded: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
      line = line.strip()
      if not line:
        continue
      try:
        loaded.append(json.loads(line))
      except json.JSONDecodeError:
        continue
    if loaded:
      self.event_buffer.extend(loaded)
    path.unlink(missing_ok=True)

  @staticmethod
  def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("type", "event"))
    if event_type == "play_start":
      event_type = "play_started"
    data = dict(event.get("data") or {})
    for key, value in event.items():
      if key not in {"type", "ts", "data"}:
        data[key] = value
    ts = event.get("ts")
    if isinstance(ts, (int, float)):
      ts_value = datetime.fromtimestamp(float(ts) / (1000 if ts > 10_000_000_000 else 1), timezone.utc).isoformat()
    elif isinstance(ts, str):
      ts_value = ts
    else:
      ts_value = datetime.now(timezone.utc).isoformat()
    return {"ts": ts_value, "type": event_type, "data": data}

  def _cpu_percent(self) -> float:
    try:
      fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
      nums = [int(x) for x in fields]
      idle = nums[3] + nums[4]
      total = sum(nums)
      prev = self._last_cpu
      self._last_cpu = (idle, total)
      if not prev:
        return self.device_info.cpu_percent
      idle_delta = idle - prev[0]
      total_delta = total - prev[1]
      if total_delta <= 0:
        return 0.0
      return round((1.0 - idle_delta / total_delta) * 100.0, 1)
    except Exception:
      try:
        return round(os.getloadavg()[0] * 100.0 / max(1, os.cpu_count() or 1), 1)
      except Exception:
        return 0.0

  @staticmethod
  def _mem_used_mb() -> float:
    try:
      mem: dict[str, int] = {}
      for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", 1)
        mem[key] = int(value.strip().split()[0])
      used_kb = mem["MemTotal"] - mem.get("MemAvailable", mem.get("MemFree", 0))
      return round(used_kb / 1024.0, 1)
    except Exception:
      return 0.0

  @staticmethod
  def _temp_c() -> float | None:
    temps: list[float] = []
    for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
      try:
        raw = Path(path).read_text(encoding="utf-8").strip()
        value = float(raw)
        temps.append(value / 1000.0 if value > 1000 else value)
      except Exception:
        continue
    return round(max(temps), 1) if temps else None

  @staticmethod
  def _wifi_ssid() -> str | None:
    try:
      proc = subprocess.run(
        ["iwgetid", "-r"],
        check=False,
        capture_output=True,
        text=True,
        timeout=0.5,
      )
      ssid = proc.stdout.strip()
      return ssid or None
    except Exception:
      return None


edge_state = EdgeState()
