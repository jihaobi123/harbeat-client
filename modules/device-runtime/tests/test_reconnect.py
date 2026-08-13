import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harbeat_device_runtime.state import ConnectionHealth, RuntimeSession, verify_expected_device


class ReconnectTests(unittest.TestCase):
  def test_same_device_can_reconnect_at_a_new_endpoint(self):
    first = verify_expected_device({"ok": True, "device_id": "rk3588-01", "session_id": "s1"}, "rk3588-01")
    second = verify_expected_device({"ok": True, "device_id": "rk3588-01", "session_id": "s2"}, "rk3588-01")
    self.assertEqual(first[0], ConnectionHealth.CONNECTED)
    self.assertEqual(second[0], ConnectionHealth.CONNECTED)
    self.assertNotEqual(first[2], second[2])

  def test_session_ttl_invalidates_old_operation_context(self):
    session = RuntimeSession("rk3588-01", "s1", 1000, 2000)
    self.assertTrue(session.is_valid(1999))
    self.assertFalse(session.is_valid(2000))
