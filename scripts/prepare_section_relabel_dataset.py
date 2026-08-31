#!/usr/bin/env python3
"""Create or refresh the human-review dataset from a SongFormer manifest."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.section_contract import canonical_structure_label
from app.modules.library.section_relabel_dataset import (
    DATASET_SCHEMA_VERSION,
    validate_dataset,
)


AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--development-root", type=Path, required=True)
    parser.add_argument("--test-root", type=Path, required=True)
    parser.add_argument("--songformer-manifest", type=Path, action="append")
    parser.add_argument("--metadata-index", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    return parser.parse_args()


def audio_files(root: Path) -> list[Path]:
    return sorted(
        path.resolve()
        for path in root.expanduser().resolve().rglob("*")
        if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
    )


def load_metadata(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {
            str(row.get("track_id") or "").strip(): dict(row)
            for row in csv.DictReader(source)
            if str(row.get("track_id") or "").strip()
        }


def load_manifests(
    paths: list[Path] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    tracks: dict[str, dict[str, Any]] = {}
    sources: list[dict[str, Any]] = []
    for path in paths or []:
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        tracks.update(
            {
                str(Path(item["audio_path"]).expanduser().resolve()): dict(item)
                for item in payload.get("tracks") or []
                if item.get("audio_path")
            }
        )
        sources.append(
            {
                "manifest_path": str(path.expanduser().resolve()),
                **{
                    key: payload.get(key)
                    for key in (
                        "model",
                        "pipeline",
                        "runner_version",
                        "label_contract_version",
                        "runtime_fingerprint",
                        "cache_namespace",
                    )
                },
            }
        )
    return tracks, {"sources": sources}


def existing_annotations(path: Path) -> dict[tuple[str, int, float, float], dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    annotations: dict[tuple[str, int, float, float], dict[str, Any]] = {}
    for track in payload.get("tracks") or []:
        track_id = str(track.get("track_id") or "")
        for index, segment in enumerate(track.get("segments") or []):
            key = (
                track_id,
                index,
                round(float(segment.get("start", 0.0)), 3),
                round(float(segment.get("end", 0.0)), 3),
            )
            if isinstance(segment.get("annotation"), dict):
                annotations[key] = dict(segment["annotation"])
    return annotations


def build_track(
    path: Path,
    *,
    split: str,
    metadata: dict[str, dict[str, str]],
    manifest_tracks: dict[str, dict[str, Any]],
    preserved: dict[tuple[str, int, float, float], dict[str, Any]],
) -> dict[str, Any]:
    track_id = path.stem
    row = metadata.get(track_id, {})
    manifest_track = manifest_tracks.get(str(path), {})
    segments: list[dict[str, Any]] = []
    for index, raw in enumerate(manifest_track.get("segments") or []):
        start = round(float(raw["start"]), 3)
        end = round(float(raw["end"]), 3)
        songformer_label = str(raw.get("label") or "unknown").strip().lower()
        key = (track_id, index, start, end)
        annotation = preserved.get(
            key,
            {
                "human_label": "",
                "human_confidence": "",
                "boundary_ok": True,
                "uncertain": False,
                "notes": "",
            },
        )
        segments.append(
            {
                "segment_index": index,
                "start": start,
                "end": end,
                "songformer_label": songformer_label,
                "structure_label_candidate": canonical_structure_label(songformer_label),
                "structure_label_probabilities": {
                    canonical_structure_label(label): float(value)
                    for label, value in dict(raw.get("label_probabilities") or {}).items()
                },
                "songformer_confidence": raw.get("label_confidence"),
                "songformer_margin": raw.get("label_margin"),
                "annotation": annotation,
            }
        )

    title = str(row.get("title") or path.stem)
    artists = str(row.get("artists") or row.get("artist") or "")
    display_name = " - ".join(value for value in (artists, title) if value) or path.stem
    return {
        "track_id": track_id,
        "split": split,
        "style": str(row.get("primary_style") or path.parent.name),
        "title": title,
        "artists": artists,
        "display_name": display_name,
        "audio_path": str(path),
        "duration": manifest_track.get("duration"),
        "songformer_status": (
            "error"
            if manifest_track.get("error")
            else "complete" if segments else "pending"
        ),
        "songformer_error": manifest_track.get("error"),
        "segments": segments,
    }


def main() -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    metadata = load_metadata(args.metadata_index)
    manifest_tracks, manifest_metadata = load_manifests(args.songformer_manifest)
    preserved = existing_annotations(output)
    development = audio_files(args.development_root)
    tests = audio_files(args.test_root)
    tracks = [
        build_track(
            path,
            split="development",
            metadata=metadata,
            manifest_tracks=manifest_tracks,
            preserved=preserved,
        )
        for path in development
    ] + [
        build_track(
            path,
            split="test",
            metadata=metadata,
            manifest_tracks=manifest_tracks,
            preserved=preserved,
        )
        for path in tests
    ]
    pending = [track["audio_path"] for track in tracks if not track["segments"]]
    if pending and args.require_complete:
        raise SystemExit(
            f"SongFormer results are missing for {len(pending)} tracks; first: {pending[0]}"
        )
    payload = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "songformer": manifest_metadata,
        "track_counts": {
            "development": len(development),
            "test": len(tests),
            "total": len(tracks),
            "pending": len(pending),
        },
        "tracks": tracks,
    }
    validation = validate_dataset(payload, require_audio=True)
    payload["validation_summary"] = validation
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    print(json.dumps(payload["track_counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
