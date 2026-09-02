#!/usr/bin/env python3
"""Attach whole-song recurrence features from cached MusicFM/MuQ tensors."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.section_relabel_dataset import validate_dataset
from app.modules.library.section_structure_context import (
    build_segment_structure_context,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--songformer-manifest", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.dataset.expanduser().read_text(encoding="utf-8"))
    manifest = json.loads(
        args.songformer_manifest.expanduser().read_text(encoding="utf-8")
    )
    records = {
        str(Path(item["audio_path"]).expanduser().resolve()): item
        for item in manifest.get("tracks") or []
        if item.get("audio_path") and not item.get("error")
    }
    cache_dir = args.cache_dir.expanduser().resolve()
    enriched = 0
    for track in payload.get("tracks") or []:
        audio_path = str(Path(track["audio_path"]).expanduser().resolve())
        record = records.get(audio_path)
        if not record:
            raise ValueError(f"SongFormer manifest has no successful record for {audio_path}")
        key = str(record["audio_fingerprint"])
        musicfm = torch.load(
            cache_dir / f"{key}.musicfm.pt", map_location="cpu", weights_only=True
        )
        muq = torch.load(
            cache_dir / f"{key}.muq.pt", map_location="cpu", weights_only=True
        )
        contexts = build_segment_structure_context(
            track["segments"],
            encoder_views={
                "musicfm_global": musicfm["global"],
                "musicfm_local": musicfm["local"],
                "muq_global": muq["global"],
                "muq_local": muq["local"],
            },
            duration=float(track.get("duration") or musicfm["duration"]),
        )
        for segment, context in zip(track["segments"], contexts):
            segment["structure_context_features"] = context
            enriched += 1

    validation = validate_dataset(payload)
    for split, status in validation["structure_context"].items():
        if not status["complete"]:
            raise ValueError(f"structure context is incomplete for {split}: {status}")
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as destination:
        json.dump(payload, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(output)
    print(json.dumps({"output": str(output), "enriched_segments": enriched, "validation": validation}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
