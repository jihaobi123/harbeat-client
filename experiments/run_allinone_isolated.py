#!/usr/bin/env python3
"""Run the official All-In-One inference path directly on original audio files.

This script intentionally imports no HarBeat analysis code and performs no
resampling, mono conversion, boundary snapping, label remapping, or consensus.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from allin1_infer import analyze


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", nargs="+", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = args.out_dir / "raw_json"
    demix_dir = args.out_dir / "_temporary_demix"
    spec_dir = args.out_dir / "_temporary_spec"
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "method": "allin1_infer.analyze(original_audio_path)",
        "model": "harmonix-all",
        "device": args.device,
        "harbeat_preprocessing": False,
        "harbeat_postprocessing": False,
        "multiprocess": False,
        "keep_byproducts": False,
        "tracks": [],
    }

    for index, audio_path in enumerate(args.audio, start=1):
        audio_path = audio_path.expanduser().resolve()
        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)

        started = time.perf_counter()
        print(f"\n[{index}/{len(args.audio)}] ORIGINAL INPUT: {audio_path}", flush=True)
        result = analyze(
            audio_path,
            out_dir=raw_dir,
            model="harmonix-all",
            device=args.device,
            include_activations=False,
            include_embeddings=False,
            demix_dir=demix_dir,
            spec_dir=spec_dir,
            keep_byproducts=False,
            overwrite=args.overwrite,
            multiprocess=False,
        )
        elapsed = time.perf_counter() - started
        segments = [
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "label": str(segment.label),
            }
            for segment in result.segments
        ]
        manifest["tracks"].append(
            {
                "path": str(result.path),
                "elapsed_seconds": round(elapsed, 3),
                "bpm": int(result.bpm),
                "beat_count": len(result.beats),
                "downbeat_count": len(result.downbeats),
                "segments": segments,
                "raw_result": str((raw_dir / audio_path.with_suffix(".json").name).resolve()),
            }
        )
        (args.out_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"[{index}/{len(args.audio)}] DONE: bpm={result.bpm}, "
            f"segments={len(segments)}, elapsed={elapsed:.1f}s",
            flush=True,
        )


if __name__ == "__main__":
    main()
