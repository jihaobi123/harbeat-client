#!/usr/bin/env python3
"""Build a deterministic SHA256 manifest without modifying source assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path, excluded_names: set[str]) -> dict[str, object]:
    root = root.resolve(strict=True)
    assets: list[dict[str, object]] = []
    for current, directories, filenames in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in excluded_names)
        for filename in sorted(filenames):
            path = Path(current, filename)
            if path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            assets.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "size_bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": sha256_file(path),
                }
            )
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "excluded_names": sorted(excluded_names),
        "file_count": len(assets),
        "total_size_bytes": sum(int(asset["size_bytes"]) for asset in assets),
        "assets": assets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--exclude-name", action="append", default=[])
    args = parser.parse_args()

    manifest = build_manifest(args.root, set(args.exclude_name))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_count": manifest["file_count"],
                "total_size_bytes": manifest["total_size_bytes"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
