#!/usr/bin/env python3
"""Create a path-sanitized, checksummed MERT artifact snapshot for Git."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np


EXCLUDED_NPZ_FIELDS = {"audio_path", "original_filename"}
EXCLUDED_RECORD_FIELDS = {"audio_path", "output_path", "original_filename"}


def _sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _publish_npz(source: Path, destination: Path) -> None:
    with np.load(source, allow_pickle=False) as payload:
        arrays = {
            key: payload[key]
            for key in payload.files
            if key not in EXCLUDED_NPZ_FIELDS
        }
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    temporary.replace(destination)


def _sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in EXCLUDED_RECORD_FIELDS
    }


def _publish_index(source: Path, destination: Path) -> None:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fields = [
        field
        for field in (rows[0].keys() if rows else [])
        if field not in EXCLUDED_RECORD_FIELDS
    ]
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})
    temporary.replace(destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if source == destination:
        raise ValueError("Source and destination must be different")
    source_tracks = sorted((source / "tracks").glob("*.npz"))
    if len(source_tracks) != 65:
        raise ValueError(f"Expected 65 source tracks, found {len(source_tracks)}")

    destination_tracks = destination / "tracks"
    destination_tracks.mkdir(parents=True, exist_ok=True)
    for index, source_path in enumerate(source_tracks, start=1):
        destination_path = destination_tracks / source_path.name
        _publish_npz(source_path, destination_path)
        print(f"[{index:02d}/{len(source_tracks)}] {source_path.name}", flush=True)

    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["dataset_root"] = "external:style_reference_v0"
    manifest["tracks"] = [_sanitize_record(record) for record in manifest["tracks"]]
    manifest["errors"] = [_sanitize_record(record) for record in manifest["errors"]]
    manifest["publication"] = {
        "audio_included": False,
        "local_paths_removed": True,
        "source_audio_bound_by_sha256": True,
    }
    _atomic_json(destination / "manifest.json", manifest)
    _publish_index(source / "index.csv", destination / "index.csv")
    shutil.copyfile(source / "README.md", destination / "README.md")
    shutil.copyfile(
        source / "official_compatibility_report.json",
        destination / "official_compatibility_report.json",
    )

    checksum_files = sorted(
        path
        for path in destination.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    checksum_lines = [
        f"{_sha256(path)}  {path.relative_to(destination).as_posix()}"
        for path in checksum_files
    ]
    (destination / "SHA256SUMS").write_text(
        "\n".join(checksum_lines) + "\n",
        encoding="utf-8",
    )

    forbidden = b"/Users/"
    contaminated = []
    for path in destination.rglob("*"):
        if path.is_file() and forbidden in path.read_bytes():
            contaminated.append(str(path.relative_to(destination)))
    if contaminated:
        raise ValueError(f"Published artifacts contain local paths: {contaminated}")
    print(f"published={destination} files={len(checksum_files)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
