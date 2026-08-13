import json
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harbeat_device_runtime.connection import (
  ConnectionProfileStore,
  ConnectionTracker,
  FailureKind,
  classify_connection_error,
)
from harbeat_device_runtime.state import ConnectionProfile, DeviceIdentity


class ConnectionTests(unittest.TestCase):
  def test_transient_timeout_keeps_last_playback_snapshot(self):
    tracker = ConnectionTracker("192.168.93.209:9000", "rk3588-01")
    tracker.record_identity(DeviceIdentity("rk3588-01"), session_id="s1", now_ms=1000)
    tracker.record_playback({"type": "playback_state", "playing": True, "position_sec": 12.5}, 1100)
    state = tracker.record_failure(TimeoutError(), 1500)
    self.assertFalse(state.connected)
    self.assertEqual(state.failure, FailureKind.TIMEOUT)
    self.assertEqual(state.playback.position_sec, 12.5)
    self.assertFalse(state.playback_is_stale(3000))

  def test_reconnects_same_device_after_hotspot_address_change(self):
    tracker = ConnectionTracker("192.168.93.209:9000", "rk3588-01")
    tracker.record_identity(DeviceIdentity("rk3588-01"), session_id="s1", now_ms=1000)
    tracker.use_endpoint("192.168.211.177:9000", now_ms=2000)
    state = tracker.record_identity(DeviceIdentity("rk3588-01"), session_id="s2", now_ms=2200)
    self.assertTrue(state.verified)
    self.assertEqual(state.endpoint, "http://192.168.211.177:9000")
    self.assertEqual(state.session_id, "s2")

  def test_wrong_device_does_not_take_over_stored_profile(self):
    tracker = ConnectionTracker("192.168.93.209:9000", "rk3588-01")
    with self.assertRaises(ValueError):
      tracker.record_identity(DeviceIdentity("rk3588-02"), session_id="s2", now_ms=1000)

  def test_classifies_network_failures(self):
    self.assertEqual(classify_connection_error(socket.timeout()), FailureKind.TIMEOUT)
    self.assertEqual(classify_connection_error(ConnectionRefusedError()), FailureKind.UNREACHABLE)
    self.assertEqual(classify_connection_error(ValueError()), FailureKind.PROTOCOL)

  def test_migrates_legacy_url_as_unverified(self):
    migrated = ConnectionProfileStore.migrate_legacy_url("192.168.93.209")
    self.assertIsNone(migrated["active_device_id"])
    self.assertEqual(migrated["unverified_endpoint"], "http://192.168.93.209:9000")
    self.assertEqual(migrated["profiles"], [])

  def test_profile_persistence_excludes_secrets_and_full_plans(self):
    raw = ConnectionProfileStore.encode([
      ConnectionProfile(
        endpoint="192.168.93.209:9000",
        identity=DeviceIdentity("rk3588-01", "RK3588"),
        last_session_id="s1",
        last_seen_ms=1000,
      )
    ], "rk3588-01")
    body = json.loads(raw)
    self.assertEqual(body["active_device_id"], "rk3588-01")
    self.assertNotIn("token", raw.lower())
    self.assertNotIn("transition_plan", raw)
    profiles, active, unverified = ConnectionProfileStore.decode(raw)
    self.assertEqual(profiles[0].identity.device_id, "rk3588-01")
    self.assertEqual(active, "rk3588-01")
    self.assertIsNone(unverified)
