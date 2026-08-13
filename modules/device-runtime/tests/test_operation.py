import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harbeat_device_runtime.operation import OperationRef, OperationStatus


class OperationTests(unittest.TestCase):
  def test_reference_is_compact_and_expires(self):
    ref = OperationRef.create(device_id="rk3588-01", session_id="s1", kind="fast_cut", now_ms=1000, ttl_ms=5000)
    body = ref.compact()
    self.assertEqual(body["status"], OperationStatus.CREATED.value)
    self.assertNotIn("transition_plan", body)
    self.assertFalse(ref.is_expired(5999))
    self.assertTrue(ref.is_expired(6000))

  def test_requires_runtime_identity(self):
    with self.assertRaises(ValueError):
      OperationRef.create(device_id="", session_id="s1", kind="fast_cut")
