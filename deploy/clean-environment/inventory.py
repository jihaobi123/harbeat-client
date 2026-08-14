#!/usr/bin/env python3
"""Read-only environment inventory; never starts, stops, or edits services."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def command_output(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def executable_inventory(name: str, version_args: list[str]) -> dict | None:
    executable = shutil.which(name)
    if executable is None:
        return None
    path = Path(executable).resolve()
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "version": command_output([str(path), *version_args]),
        "dpkg_owner": command_output(["dpkg-query", "-S", str(path)]),
    }


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
        "systemd_running": command_output(["systemctl", "list-units", "--type=service", "--state=running", "--no-pager", "--no-legend"]),
        "active_ports": command_output(["ss", "-ltnup"]),
        "os_release": command_output(["cat", "/etc/os-release"]),
        "system_packages": command_output(
            ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${Architecture}\\n"]
        ),
        "python_executable": command_output(["python3", "-c", "import sys; print(sys.executable)"]),
        "python_packages": command_output(["python3", "-m", "pip", "freeze", "--all"]),
        "executables": {
            "ffmpeg": executable_inventory("ffmpeg", ["-version"]),
            "ffprobe": executable_inventory("ffprobe", ["-version"]),
        },
        "cuda": command_output(["bash", "-lc", "command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || true"]),
        "jetson_release": command_output(["bash", "-lc", "test -r /etc/nv_tegra_release && cat /etc/nv_tegra_release || true"]),
        "audio_devices": command_output(["bash", "-lc", "command -v aplay >/dev/null && aplay -l || true"]),
        "usb_devices": command_output(["bash", "-lc", "command -v lsusb >/dev/null && lsusb || true"]),
        "pci_devices": command_output(["bash", "-lc", "command -v lspci >/dev/null && lspci -nn || true"]),
        "network_links": command_output(["bash", "-lc", "command -v ip >/dev/null && ip -json link || true"]),
        "disk": shutil.disk_usage(root)._asdict(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(local_inventory(args.root.resolve()), indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(payload)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
