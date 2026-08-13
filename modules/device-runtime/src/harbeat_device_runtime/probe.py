"""Read-only compatibility probe for a deployed RK edge agent."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .endpoint import RkEndpoint
from .state import parse_health, parse_playback


class ProbeError(RuntimeError):
  pass


def _get_json(url: str, timeout_sec: float) -> tuple[dict[str, Any], float]:
  started = time.perf_counter()
  try:
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout_sec) as response:
      if response.status != 200:
        raise ProbeError(f"GET {url} returned HTTP {response.status}")
      raw = response.read(1_048_577)
  except (HTTPError, URLError, TimeoutError, OSError) as exc:
    raise ProbeError(f"GET {url} failed: {exc.__class__.__name__}") from exc
  elapsed = time.perf_counter() - started
  if len(raw) > 1_048_576:
    raise ProbeError(f"GET {url} response exceeds 1 MiB")
  try:
    body = json.loads(raw.decode("utf-8"))
  except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise ProbeError(f"GET {url} returned invalid JSON") from exc
  if not isinstance(body, dict):
    raise ProbeError(f"GET {url} returned a non-object JSON value")
  return body, elapsed


def probe_runtime(base_url: str, timeout_sec: float = 3.0) -> dict[str, Any]:
  endpoint = RkEndpoint.parse(base_url)
  health_raw, health_sec = _get_json(f"{endpoint.url}/health", timeout_sec)
  state_raw, state_sec = _get_json(f"{endpoint.url}/state", timeout_sec)
  health, identity, session_id = parse_health(health_raw)
  playback = parse_playback(state_raw)
  return {
    "contract_version": "device-runtime/v0.1.0",
    "reachable": True,
    "health": health.value,
    "identity_status": "verified" if identity.device_id else "pending_pairing_identity",
    "device_id": identity.device_id or None,
    "session_present": bool(session_id),
    "audio_ready": bool(health_raw.get("audio_ready")),
    "playback": {
      "playing": playback.playing,
      "paused": playback.paused,
      "has_current_song": playback.current_song_id is not None,
      "position_sec": playback.position_sec,
      "duration_sec": playback.duration_sec,
      "playback_tier": playback.playback_tier,
      "has_scheduled_render": playback.scheduled_default_render is not None,
    },
    "latency_ms": {
      "health": round(health_sec * 1000, 2),
      "state": round(state_sec * 1000, 2),
      "total": round((health_sec + state_sec) * 1000, 2),
    },
  }
