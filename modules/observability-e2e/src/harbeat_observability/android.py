"""Small ADB adapter that always acts on a freshly captured semantic frame."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .ui_semantics import SemanticControl, find_control, parse_controls


class AndroidControlError(RuntimeError):
    pass


@dataclass
class AndroidDevice:
    serial: str
    adb_path: str = "adb"

    def _run(self, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.adb_path, "-s", self.serial, *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            raise AndroidControlError(f"adb command failed: {' '.join(args)}: {exc}") from exc

    def capture_controls(self) -> list[SemanticControl]:
        remote = "/sdcard/harbeat-observability-ui.xml"
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp) / "ui.xml"
            self._run("shell", "uiautomator", "dump", remote, timeout=35.0)
            self._run("pull", remote, str(local), timeout=20.0)
            return parse_controls(local)

    def find_fresh_control(
        self,
        label: str,
        *,
        resource_id: str | None = None,
        exact: bool = True,
    ) -> SemanticControl | None:
        return find_control(
            self.capture_controls(),
            label,
            resource_id=resource_id,
            exact=exact,
        )

    def tap_fresh_control(
        self,
        label: str,
        *,
        resource_id: str | None = None,
        exact: bool = True,
    ) -> SemanticControl:
        control = self.find_fresh_control(label, resource_id=resource_id, exact=exact)
        if control is None:
            raise AndroidControlError(f"enabled clickable control not found: {label}")
        x, y = control.center
        self._run("shell", "input", "tap", str(x), str(y), timeout=10.0)
        return control

