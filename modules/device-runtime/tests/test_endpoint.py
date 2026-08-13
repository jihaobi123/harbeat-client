import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harbeat_device_runtime.endpoint import EndpointError, RkEndpoint


class EndpointTests(unittest.TestCase):
  def test_adds_default_port_and_removes_trailing_slash(self):
    self.assertEqual(RkEndpoint.parse("192.168.93.209/").url, "http://192.168.93.209:9000")

  def test_preserves_explicit_port_and_normalizes_host(self):
    self.assertEqual(RkEndpoint.parse("HTTP://RK3588:19000").url, "http://rk3588:19000")

  def test_rejects_credentials_and_paths(self):
    for value in ("http://cat:temppwd@rk:9000", "http://rk:9000/api"):
      with self.subTest(value=value):
        with self.assertRaises(EndpointError):
          RkEndpoint.parse(value)
