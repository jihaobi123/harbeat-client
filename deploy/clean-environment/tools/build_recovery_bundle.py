#!/usr/bin/env python3
"""Create a read-only device recovery bundle over SSH."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REMOTE_COMMAND = r"""
set -eu
paths=''
for path in \
  /boot \
  /etc/udev/rules.d \
  /etc/modprobe.d \
  /etc/alsa \
  /etc/asound.conf \
  /etc/security/limits.d \
  /etc/systemd/system \
  /etc/nv_tegra_release \
  /usr/bin/ffmpeg
do
  if [ -e "$path" ]; then paths="$paths $path"; fi
done
tar --create --gzip --file=- --ignore-failed-read --warning=no-file-changed \
  --exclude='*/NetworkManager/*' \
  --exclude='*/.env' \
  --exclude='*/.env.*' \
  --exclude='*secret*' \
  --exclude='*credential*' \
  --exclude='*cypher*' \
  --exclude='*harbeat*' \
  --exclude='*connect-wow0110*' \
  $paths
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("rk3588", "jetson"), required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    archive = output_root / f"{args.role}-recovery-{stamp}.tar.gz"
    with archive.open("wb") as output:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                args.host,
                "bash -s",
            ],
            input=REMOTE_COMMAND.encode("utf-8"),
            stdout=output,
            stderr=subprocess.PIPE,
            check=False,
        )
    if result.returncode != 0:
        archive.unlink(missing_ok=True)
        print(result.stderr.decode("utf-8", errors="replace"))
        return result.returncode

    manifest = {
        "schema_version": 1,
        "role": args.role,
        "host": args.host,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "archive": archive.name,
        "sha256": sha256(archive),
        "transport": "ssh-stdout-tar",
        "remote_mutation": False,
        "included_categories": ["boot", "udev", "kernel-module-config", "alsa", "limits", "systemd-inventory", "jetson-release", "ffmpeg-binary"],
        "excluded_categories": ["network-secrets", "old-source", "venv", "site-packages", "render-cache", "logs", "task-state"],
        "restore_policy": "Restore only onto the same hardware model after base-image verification; never source new runtime code from this archive.",
    }
    manifest_path = archive.with_suffix(archive.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
