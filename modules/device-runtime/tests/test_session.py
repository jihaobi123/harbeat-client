import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harbeat_device_runtime.operation import OperationRef
from harbeat_device_runtime.session import SessionBinding
from harbeat_device_runtime.state import RuntimeSession


class SessionBindingTests(unittest.TestCase):
  def _operation(self,device='rk-1',session='s1'):
    return OperationRef.create(device_id=device,session_id=session,kind='fast',now_ms=1000,ttl_ms=5000)

  def test_accepts_only_current_device_and_session(self):
    binding=SessionBinding(RuntimeSession('rk-1','s1',1000,5000))
    self.assertTrue(binding.accepts(self._operation(),2000))
    self.assertFalse(binding.accepts(self._operation(session='s2'),2000))
    self.assertFalse(binding.accepts(self._operation(device='rk-2'),2000))

  def test_rejects_expired_session_or_operation(self):
    binding=SessionBinding(RuntimeSession('rk-1','s1',1000,2000))
    self.assertFalse(binding.accepts(self._operation(),2000))
    with self.assertRaises(ValueError): binding.require(self._operation(),2000)
