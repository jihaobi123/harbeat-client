#!/usr/bin/env python3
"""Verify external recovery archives and emit a non-sensitive evidence index."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path


FORBIDDEN = (
    "networkmanager/system-connections",
    "/.env",
    "secret",
    "credential",
    "site-packages",
    "venv",
    "render-cache",
    "/var/log/",
    "cypher",
    "harbeat",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive = manifest_path.parent / manifest["archive"]
    actual_sha256 = sha256(archive)
    with tarfile.open(archive, "r:gz") as handle:
        entries = handle.getnames()
    forbidden_entries = sorted(
        entry for entry in entries if any(value in entry.lower() for value in FORBIDDEN)
    )
    return {
        "role": manifest["role"],
        "archive_uri": f"external://harbeat-device-backups/20260814/accepted/{archive.name}",
        "size_bytes": archive.stat().st_size,
        "sha256": actual_sha256,
        "manifest_sha256": manifest["sha256"],
        "sha256_matches": actual_sha256 == manifest["sha256"],
        "entry_count": len(entries),
        "forbidden_entries": forbidden_entries,
        "readable": True,
        "remote_mutation": manifest.get("remote_mutation"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    bundles = [verify(path) for path in sorted(args.backup_root.glob("*.tar.gz.manifest.json"))]
    passed = (
        {item["role"] for item in bundles} == {"rk3588", "jetson"}
        and all(item["sha256_matches"] and not item["forbidden_entries"] for item in bundles)
    )
    report = {
        "schema_version": 1,
        "audit": "r1-external-recovery-bundles",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bundles": bundles,
        "passed": passed,
        "whole_disk_image_created": False,
        "empty_device_restore_tested": False,
        "cleanup_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
