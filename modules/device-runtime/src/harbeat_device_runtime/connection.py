"""Connection lifecycle independent from Flutter widget state."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .endpoint import RkEndpoint
from .state import ConnectionProfile, DeviceIdentity, PlaybackState, parse_playback


class FailureKind(str, Enum):
  TIMEOUT = "timeout"
  UNREACHABLE = "unreachable"
  PROTOCOL = "protocol"


def classify_connection_error(error: BaseException) -> FailureKind:
  if isinstance(error, (TimeoutError, socket.timeout)):
    return FailureKind.TIMEOUT
  if isinstance(error, (ConnectionError, OSError)):
    return FailureKind.UNREACHABLE
  return FailureKind.PROTOCOL


@dataclass(frozen=True, slots=True)
class ConnectionSnapshot:
  endpoint: str
  device_id: str | None
  session_id: str | None
  connected: bool
  verified: bool
  observed_at_ms: int
  last_success_ms: int | None = None
  consecutive_failures: int = 0
  failure: FailureKind | None = None
  playback: PlaybackState | None = None

  def playback_is_stale(self, now_ms: int, stale_after_ms: int = 5_000) -> bool:
    return self.last_success_ms is None or now_ms - self.last_success_ms > stale_after_ms


class ConnectionTracker:
  """Owns one device connection without performing network I/O itself."""

  def __init__(self, endpoint: str, expected_device_id: str | None = None) -> None:
    normalized = RkEndpoint.parse(endpoint).url
    self._snapshot = ConnectionSnapshot(
      endpoint=normalized,
      device_id=expected_device_id,
      session_id=None,
      connected=False,
      verified=False,
      observed_at_ms=0,
    )

  @property
  def snapshot(self) -> ConnectionSnapshot:
    return self._snapshot

  def use_endpoint(self, endpoint: str, now_ms: int) -> ConnectionSnapshot:
    normalized = RkEndpoint.parse(endpoint).url
    self._snapshot = replace(
      self._snapshot,
      endpoint=normalized,
      connected=False,
      verified=False,
      observed_at_ms=now_ms,
      failure=None,
      consecutive_failures=0,
    )
    return self._snapshot

  def record_identity(
    self,
    identity: DeviceIdentity,
    *,
    session_id: str | None,
    now_ms: int,
  ) -> ConnectionSnapshot:
    if not identity.device_id:
      raise ValueError("device identity is required before binding an endpoint")
    expected = self._snapshot.device_id
    if expected and expected != identity.device_id:
      raise ValueError(f"device mismatch: expected {expected}, got {identity.device_id}")
    self._snapshot = replace(
      self._snapshot,
      device_id=identity.device_id,
      session_id=session_id,
      connected=True,
      verified=True,
      observed_at_ms=now_ms,
      last_success_ms=now_ms,
      failure=None,
      consecutive_failures=0,
    )
    return self._snapshot

  def record_playback(self, payload: Mapping[str, Any], now_ms: int) -> ConnectionSnapshot:
    playback = parse_playback(payload)
    self._snapshot = replace(
      self._snapshot,
      connected=True,
      observed_at_ms=now_ms,
      last_success_ms=now_ms,
      consecutive_failures=0,
      failure=None,
      playback=playback,
    )
    return self._snapshot

  def record_failure(self, error: BaseException, now_ms: int) -> ConnectionSnapshot:
    kind = classify_connection_error(error)
    self._snapshot = replace(
      self._snapshot,
      connected=False,
      observed_at_ms=now_ms,
      consecutive_failures=self._snapshot.consecutive_failures + 1,
      failure=kind,
    )
    return self._snapshot


class ConnectionProfileStore:
  """JSON persistence for identity and endpoint only; never stores tokens."""

  VERSION = 1

  @staticmethod
  def migrate_legacy_url(raw_url: str) -> dict[str, Any]:
    return {
      "version": ConnectionProfileStore.VERSION,
      "active_device_id": None,
      "unverified_endpoint": RkEndpoint.parse(raw_url).url,
      "profiles": [],
    }

  @staticmethod
  def encode(profiles: list[ConnectionProfile], active_device_id: str | None) -> str:
    body = {
      "version": ConnectionProfileStore.VERSION,
      "active_device_id": active_device_id,
      "unverified_endpoint": None,
      "profiles": [
        {
          "device_id": profile.identity.device_id,
          "model": profile.identity.model,
          "endpoint": RkEndpoint.parse(profile.endpoint).url,
          "last_session_id": profile.last_session_id,
          "last_seen_ms": profile.last_seen_ms,
        }
        for profile in profiles
      ],
    }
    return json.dumps(body, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

  @staticmethod
  def decode(raw: str) -> tuple[list[ConnectionProfile], str | None, str | None]:
    body = json.loads(raw)
    if body.get("version") != ConnectionProfileStore.VERSION:
      raise ValueError("unsupported connection profile version")
    profiles = []
    seen = set()
    for item in body.get("profiles") or []:
      device_id = str(item.get("device_id") or "").strip()
      if not device_id or device_id in seen:
        continue
      seen.add(device_id)
      profiles.append(ConnectionProfile(
        endpoint=RkEndpoint.parse(str(item.get("endpoint") or "")).url,
        identity=DeviceIdentity(device_id=device_id, model=str(item.get("model") or "")),
        last_session_id=(str(item["last_session_id"]) if item.get("last_session_id") else None),
        last_seen_ms=(int(item["last_seen_ms"]) if item.get("last_seen_ms") is not None else None),
      ))
    active = body.get("active_device_id")
    unverified = body.get("unverified_endpoint")
    return profiles, str(active) if active else None, RkEndpoint.parse(unverified).url if unverified else None

