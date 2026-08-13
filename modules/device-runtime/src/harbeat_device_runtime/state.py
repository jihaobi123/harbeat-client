"""Bounded DTOs for RK health and playback responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ConnectionHealth(str, Enum):
  CONNECTED = "connected"
  TRANSIENT_FAILURE = "transient_failure"
  DEVICE_MISMATCH = "device_mismatch"
  PROTOCOL_ERROR = "protocol_error"


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
  device_id: str
  model: str = ""


@dataclass(frozen=True, slots=True)
class ConnectionProfile:
  endpoint: str
  identity: DeviceIdentity
  last_session_id: str | None = None
  last_seen_ms: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeSession:
  device_id: str
  session_id: str
  created_at_ms: int
  expires_at_ms: int

  def is_valid(self, now_ms: int) -> bool:
    return now_ms < self.expires_at_ms


@dataclass(frozen=True, slots=True)
class PlaybackState:
  timestamp_ms: int
  playing: bool
  paused: bool
  current_song_id: str | int | None
  position_sec: float
  duration_sec: float
  next_song_id: str | int | None = None
  playback_tier: str = "basic"
  scheduled_default_render: Mapping[str, Any] | None = None


def _id(value: Any) -> str | int | None:
  if isinstance(value, (str, int)):
    return value
  if isinstance(value, float) and value.is_integer():
    return int(value)
  return None


def _number(value: Any, default: float = 0.0) -> float:
  try:
    result = float(value)
  except (TypeError, ValueError):
    return default
  return max(0.0, result)


def parse_health(payload: Mapping[str, Any]) -> tuple[ConnectionHealth, DeviceIdentity, str | None]:
  if not isinstance(payload, Mapping) or payload.get("ok") is not True:
    return ConnectionHealth.PROTOCOL_ERROR, DeviceIdentity(""), None
  device_id = payload.get("device_id") or payload.get("rk_id")
  identity = DeviceIdentity(
    device_id=device_id.strip() if isinstance(device_id, str) else "",
    model=str(payload.get("model") or ""),
  )
  session = payload.get("session_id")
  return ConnectionHealth.CONNECTED, identity, session if isinstance(session, str) else None


def verify_expected_device(
  payload: Mapping[str, Any], expected_device_id: str,
) -> tuple[ConnectionHealth, DeviceIdentity, str | None]:
  health, identity, session = parse_health(payload)
  if health is not ConnectionHealth.CONNECTED:
    return health, identity, session
  if not identity.device_id:
    return ConnectionHealth.PROTOCOL_ERROR, identity, session
  if identity.device_id != expected_device_id:
    return ConnectionHealth.DEVICE_MISMATCH, identity, session
  return health, identity, session


def parse_playback(payload: Mapping[str, Any]) -> PlaybackState:
  if payload.get("type") not in {None, "playback_state"}:
    raise ValueError("unexpected RK playback response type")
  return PlaybackState(
    timestamp_ms=int(payload.get("ts") or 0),
    playing=bool(payload.get("playing", False)),
    paused=bool(payload.get("paused", False)),
    current_song_id=_id(payload.get("current_song_id")),
    position_sec=_number(payload.get("position_sec")),
    duration_sec=_number(payload.get("duration_sec")),
    next_song_id=_id(payload.get("next_song_id")),
    playback_tier=str(payload.get("playback_tier") or "basic"),
    scheduled_default_render=(
      dict(payload["scheduled_default_render"])
      if isinstance(payload.get("scheduled_default_render"), Mapping)
      else None
    ),
  )
