#!/usr/bin/env python3
"""Collect a read-only inventory over SSH without creating files on the device."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "deploy" / "clean-environment" / "inventory.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("rk3588", "jetson"), required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    script = INVENTORY.read_bytes()
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            args.host,
            "python3 - --root /",
        ],
        input=script,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.buffer.write(result.stderr)
        return result.returncode
    payload = json.loads(result.stdout)
    payload["collection"] = {
        "transport": "ssh-stdin-only",
        "role": args.role,
        "host": args.host,
        "remote_mutation": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
