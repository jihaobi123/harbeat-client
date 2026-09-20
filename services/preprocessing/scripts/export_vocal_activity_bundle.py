#!/usr/bin/env python3
"""Export small vocal JSON overlays; never duplicate or modify the audio bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.modules.library.vocal_activity import storage_path
from app.modules.library.same_style_preprocess import _sha256


def export_bundle(root: Path, index_key: str, destination: Path) -> dict:
    index_path = storage_path(root, index_key)
    index = json.loads(index_path.read_text())
    if index["processed_tracks"] != index["total_tracks"]:
        raise ValueError("vocal backfill still incomplete")
    if any(item["status"] != "ready" for item in index["items"]):
        raise ValueError("failed tracks cannot be shipped as a complete bundle")
    paths = {index_key: index_path}
    for item in index["items"]:
        report_key = item["vocal_activity_storage_key"]
        report_path = storage_path(root, report_key)
        if _sha256(report_path) != item["vocal_activity_sha256"]:
            raise ValueError("report hash mismatch")
        if _sha256(storage_path(root, item["manifest_storage_key"])) != item["manifest_sha256"]:
            raise ValueError("base manifest hash mismatch")
        success_path = report_path.parent / "_SUCCESS.json"
        if json.loads(success_path.read_text())["vocal_activity_sha256"] != item["vocal_activity_sha256"]:
            raise ValueError("success marker mismatch")
        paths[report_key] = report_path
        paths[success_path.relative_to(root.resolve()).as_posix()] = success_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: never overwrite an earlier delivered bundle.
    with ZipFile(destination, "x", compression=ZIP_DEFLATED) as bundle:
        for key, path in sorted(paths.items()):
            bundle.write(path, key)
        bundle.write(ROOT / "docs/jetson_vocal_activity_handoff_v1.md", "VOCAL_ACTIVITY_README.md")
    with ZipFile(destination) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("ZIP CRC validation failed")
    return {"path": str(destination), "tracks": index["total_tracks"], "sha256": _sha256(destination),
            "size_bytes": destination.stat().st_size,
            "instructions": "Extract into HARBEAT_PREPROCESS_ROOT (the directory containing published/). Audio not included."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_bundle(args.root.resolve(), args.index, args.output), ensure_ascii=False))
