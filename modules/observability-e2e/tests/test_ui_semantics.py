from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from harbeat_observability.ui_semantics import find_control, parse_controls


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "flutter_confirm.xml"


class UiSemanticsTests(unittest.TestCase):
    def test_finds_utf8_flutter_confirm_button(self) -> None:
        control = find_control(parse_controls(FIXTURE), "确认切歌")

        self.assertIsNotNone(control)
        assert control is not None
        self.assertEqual(control.center, (323, 759))
        self.assertTrue(control.clickable)

    def test_does_not_accept_mojibake_label(self) -> None:
        control = find_control(parse_controls(FIXTURE), "纭鍒囨瓕")
        self.assertIsNone(control)

    def test_ignores_non_clickable_container(self) -> None:
        controls = parse_controls(FIXTURE)
        control = find_control(controls, "能量切歌", exact=False)
        self.assertIsNone(control)


if __name__ == "__main__":
    unittest.main()

