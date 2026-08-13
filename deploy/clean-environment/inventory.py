#!/usr/bin/env python3
"""Read-only environment inventory; never starts, stops, or edits services."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def command_output(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def local_inventory(root: Path) -> dict:
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only",
        "host": platform.node(),
        "os": platform.platform(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "git_head": command_output(["git", "-C", str(root), "rev-parse", "HEAD"]),
        "git_branch": command_output(["git", "-C", str(root), "branch", "--show-current"]),
        "systemd_units": command_output(["systemctl", "list-unit-files", "--type=service", "--no-pager", "--no-legend"]),
        "active_ports": command_output(["ss", "-ltnup"]),
        "python_executable": command_output(["python3", "-c", "import sys; print(sys.executable)"]),
        "cuda": command_output(["bash", "-lc", "command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || true"]),
        "audio_devices": command_output(["bash", "-lc", "command -v aplay >/dev/null && aplay -l || true"]),
        "disk": shutil.disk_usage(root)._asdict(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(local_inventory(args.root.resolve()), indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
