import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harbeat_device_runtime.probe import ProbeError, probe_runtime


class ProbeTests(unittest.TestCase):
  @patch("harbeat_device_runtime.probe._get_json")
  def test_report_is_bounded_and_redacted(self, get_json):
    health = json.loads((Path(__file__).parent / "fixtures" / "rk_health.json").read_text(encoding="utf-8"))
    state = json.loads((Path(__file__).parent / "fixtures" / "rk_state.json").read_text(encoding="utf-8"))
    get_json.side_effect = [(health, 0.02), (state, 0.03)]
    report = probe_runtime("192.168.93.209:9000")
    rendered = json.dumps(report)
    self.assertTrue(report["reachable"])
    self.assertEqual(report["identity_status"], "pending_pairing_identity")
    self.assertEqual(report["latency_ms"]["total"], 50.0)
    self.assertNotIn("song-redacted", rendered)
    self.assertNotIn("session-redacted", rendered)
    self.assertNotIn("audio_socket", rendered)

  @patch("harbeat_device_runtime.probe.urlopen")
  def test_network_error_does_not_leak_endpoint_details(self, urlopen):
    urlopen.side_effect = TimeoutError("private host detail")
    with self.assertRaisesRegex(ProbeError, "TimeoutError") as caught:
      probe_runtime("192.168.93.209:9000")
    self.assertNotIn("private host detail", str(caught.exception))
