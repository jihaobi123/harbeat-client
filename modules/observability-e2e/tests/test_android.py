from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from harbeat_observability.android import AndroidDevice


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "flutter_confirm.xml"


class AndroidTests(unittest.TestCase):
    def test_tap_uses_control_from_fresh_capture(self) -> None:
        device = AndroidDevice("phone")
        calls: list[tuple[str, ...]] = []

        def fake_run(*args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[0] == "pull":
                Path(args[2]).write_bytes(FIXTURE.read_bytes())
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(device, "_run", side_effect=fake_run):
            control = device.tap_fresh_control("确认切歌")

        self.assertEqual(control.center, (323, 759))
        self.assertEqual(calls[0][0:3], ("shell", "uiautomator", "dump"))
        self.assertEqual(calls[-1], ("shell", "input", "tap", "323", "759"))


if __name__ == "__main__":
    unittest.main()

