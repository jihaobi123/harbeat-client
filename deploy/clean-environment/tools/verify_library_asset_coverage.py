#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def relative_asset_path(raw: object) -> str:
    normalized = str(raw or "").replace("\\", "/")
    marker = "/music-files/"
    if marker not in normalized:
        return ""
    return normalized.split(marker, 1)[1].lstrip("/")


def verify(index: list[dict[str, object]], manifest: dict[str, object]) -> dict[str, object]:
    manifest_assets = manifest.get("assets") or []
    available = {
        str(item.get("relative_path") or "")
        for item in manifest_assets
        if isinstance(item, dict)
    }
    missing: list[dict[str, str]] = []
    source_ready = 0
    songs_with_stem_manifest = 0
    songs_without_stem_manifest: list[str] = []
    stem_ready = 0
    stem_expected = 0
    for song in index:
        song_id = str(song.get("id") or "")
        source = relative_asset_path(song.get("source_path"))
        if source and source in available:
            source_ready += 1
        else:
            missing.append({"song_id": song_id, "role": "source", "relative_path": source})
        stems = song.get("stems") or {}
        if not isinstance(stems, dict):
            stems = {}
        declared = {role: stems.get(role) for role in ("vocals", "drums", "bass", "other")}
        if not any(declared.values()):
            songs_without_stem_manifest.append(song_id)
            continue
        songs_with_stem_manifest += 1
        for role in ("vocals", "drums", "bass", "other"):
            stem_expected += 1
            stem = relative_asset_path(declared.get(role))
            if stem and stem in available:
                stem_ready += 1
            else:
                missing.append({"song_id": song_id, "role": role, "relative_path": stem})
    return {
        "schema_version": 1,
        "library_songs": len(index),
        "source_files_ready": source_ready,
        "songs_with_stem_manifest": songs_with_stem_manifest,
        "songs_without_stem_manifest": songs_without_stem_manifest,
        "declared_stem_files_expected": stem_expected,
        "declared_stem_files_ready": stem_ready,
        "missing": missing,
        "passed": not missing and source_ready == len(index) and stem_ready == stem_expected,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = verify(index, manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
