import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harbeat_device_runtime.state import (
  ConnectionHealth,
  parse_health,
  parse_playback,
  verify_expected_device,
)


class StateTests(unittest.TestCase):
  def test_real_health_shape_is_reachable_but_identity_is_pending(self):
    health, identity, session = parse_health({
      "ok": True,
      "audio_ready": True,
      "current_song_id": "song-a",
      "session_id": "session-a",
      "sync_status": {"running": False},
    })
    self.assertEqual(health, ConnectionHealth.CONNECTED)
    self.assertEqual(identity.device_id, "")
    self.assertEqual(session, "session-a")

  def test_parses_real_health_shape_without_retaining_private_fields(self):
    health, identity, session = parse_health({
      "ok": True,
      "audio_ready": True,
      "current_song_id": "song-a",
      "session_id": "session-a",
      "device_id": "rk3588-01",
      "token": "must-not-be-copied",
    })
    self.assertEqual(health, ConnectionHealth.CONNECTED)
    self.assertEqual(identity.device_id, "rk3588-01")
    self.assertEqual(session, "session-a")

  def test_health_without_identity_cannot_bind_a_stored_device(self):
    health, _, _ = verify_expected_device(
      {"ok": True, "session_id": "session-a"},
      "rk3588-01",
    )
    self.assertEqual(health, ConnectionHealth.PROTOCOL_ERROR)

  def test_rejects_wrong_device_after_hotspot_ip_change(self):
    health, identity, _ = verify_expected_device(
      {"ok": True, "device_id": "another-rk", "session_id": "s2"},
      "rk3588-01",
    )
    self.assertEqual(health, ConnectionHealth.DEVICE_MISMATCH)
    self.assertEqual(identity.device_id, "another-rk")

  def test_bounds_invalid_playback_numbers(self):
    state = parse_playback({"type": "playback_state", "ts": 1, "position_sec": -4, "duration_sec": "bad"})
    self.assertEqual(state.position_sec, 0.0)
    self.assertEqual(state.duration_sec, 0.0)
