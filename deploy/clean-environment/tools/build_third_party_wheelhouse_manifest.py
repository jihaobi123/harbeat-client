#!/usr/bin/env python3
"""Build a deterministic hash manifest for an external target wheelhouse."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, choices=("rk3588", "jetson"))
    parser.add_argument("--wheelhouse", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    wheelhouse = args.wheelhouse.resolve()
    artifacts = [
        {
            "name": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(wheelhouse.glob("*.whl"), key=lambda item: item.name.lower())
        if path.stat().st_size > 0
    ]
    payload = {
        "schema_version": 1,
        "profile": args.profile,
        "source": f"external://harbeat-device-backups/20260814/third-party-{args.profile}-locked",
        "artifacts": artifacts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"profile": args.profile, "artifacts": len(artifacts)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
