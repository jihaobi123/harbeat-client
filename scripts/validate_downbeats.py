#!/usr/bin/env python3
"""Run isolated downbeat inference routes and build an auditable report.

Each model runs in a fresh subprocess.  This avoids retaining Beat This,
All-In-One and madmom model weights in the same process on small machines.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.analysis import (  # noqa: E402
    _analyze_downbeats_madmom,
    _analyze_rhythm_all_in_one,
    _analyze_rhythm_beat_this,
    _downbeat_match_metrics,
)


ENGINES = {
    "beat_this": _analyze_rhythm_beat_this,
    "all_in_one": _analyze_rhythm_all_in_one,
    "madmom": _analyze_downbeats_madmom,
}


def _jsonable(result: dict, elapsed: float) -> dict:
    return {
        "engine": result.get("engine"),
        "elapsed_seconds": round(elapsed, 3),
        "confidence": result.get("confidence"),
        "bpm": result.get("bpm"),
        "beat_times": [round(float(value), 4) for value in result.get("beat_times", [])],
        "downbeats": [round(float(value), 4) for value in result.get("downbeats", [])],
        "beat_positions": [int(value) for value in result.get("beat_positions", [])],
    }


def infer(engine: str, track: Path, output: Path) -> None:
    started = time.time()
    y, sr = librosa.load(track, sr=22050, mono=True)
    result = ENGINES[engine](y, sr)
    payload = {
        "track": track.name,
        "duration_seconds": round(len(y) / sr, 3),
        "sample_rate": sr,
        **_jsonable(result, time.time() - started),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_batch(input_dir: Path, output_dir: Path) -> None:
    tracks = sorted(path for path in input_dir.iterdir() if path.suffix.lower() in {".mp3", ".wav", ".flac", ".m4a"})
    output_dir.mkdir(parents=True, exist_ok=True)
    for track_index, track in enumerate(tracks, start=1):
        stem_dir = output_dir / track.stem
        for engine in ENGINES:
            output = stem_dir / f"{engine}.json"
            if output.exists():
                print(f"[{track_index}/{len(tracks)}] {track.name} {engine}: cached", flush=True)
                continue
            print(f"[{track_index}/{len(tracks)}] {track.name} {engine}: running", flush=True)
            command = [sys.executable, str(Path(__file__).resolve()), "infer", "--engine", engine, "--track", str(track), "--output", str(output)]
            completed = subprocess.run(command, cwd=ROOT, text=True)
            if completed.returncode:
                error = {"track": track.name, "engine": engine, "error": f"exit_code={completed.returncode}"}
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(error, ensure_ascii=False, indent=2), encoding="utf-8")


def summarize(output_dir: Path) -> None:
    rows = []
    for stem_dir in sorted(path for path in output_dir.iterdir() if path.is_dir()):
        results = {}
        for engine in ENGINES:
            path = stem_dir / f"{engine}.json"
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                if "error" not in payload:
                    results[engine] = payload
        pairs = {}
        names = list(results)
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                pairs[f"{first}:{second}"] = _downbeat_match_metrics(
                    results[first]["downbeats"], results[second]["downbeats"], tolerance=0.07
                )
        rows.append({
            "track": next(iter(results.values())).get("track", stem_dir.name) if results else stem_dir.name,
            "duration_seconds": next(iter(results.values())).get("duration_seconds") if results else None,
            "engines_available": list(results),
            "downbeat_counts": {name: len(value["downbeats"]) for name, value in results.items()},
            "pair_metrics": pairs,
        })
    (output_dir / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def click_track(
    track: Path,
    predictions: Path,
    output: Path,
    *,
    start_seconds: float = 0.0,
    duration_seconds: float | None = None,
) -> None:
    payload = json.loads(predictions.read_text(encoding="utf-8"))
    y, sr = librosa.load(track, sr=22050, mono=True)
    beat_clicks = librosa.clicks(times=np.asarray(payload.get("beat_times", [])), sr=sr, click_freq=900.0, length=len(y))
    bar_clicks = librosa.clicks(times=np.asarray(payload.get("downbeats", [])), sr=sr, click_freq=1800.0, length=len(y))
    mixed = np.clip(0.78 * y + 0.12 * beat_clicks + 0.28 * bar_clicks, -1.0, 1.0)
    start_sample = max(0, int(round(start_seconds * sr)))
    end_sample = len(mixed) if duration_seconds is None else min(
        len(mixed), start_sample + int(round(duration_seconds * sr))
    )
    mixed = mixed[start_sample:end_sample]
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output, mixed, sr, subtype="PCM_16")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    infer_parser = subparsers.add_parser("infer")
    infer_parser.add_argument("--engine", choices=ENGINES, required=True)
    infer_parser.add_argument("--track", type=Path, required=True)
    infer_parser.add_argument("--output", type=Path, required=True)
    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("--input-dir", type=Path, required=True)
    batch_parser.add_argument("--output-dir", type=Path, required=True)
    summary_parser = subparsers.add_parser("summarize")
    summary_parser.add_argument("--output-dir", type=Path, required=True)
    click_parser = subparsers.add_parser("click")
    click_parser.add_argument("--track", type=Path, required=True)
    click_parser.add_argument("--predictions", type=Path, required=True)
    click_parser.add_argument("--output", type=Path, required=True)
    click_parser.add_argument("--start", type=float, default=0.0)
    click_parser.add_argument("--duration", type=float)
    args = parser.parse_args()
    if args.command == "infer":
        infer(args.engine, args.track, args.output)
    elif args.command == "batch":
        run_batch(args.input_dir, args.output_dir)
    elif args.command == "summarize":
        summarize(args.output_dir)
    else:
        click_track(
            args.track,
            args.predictions,
            args.output,
            start_seconds=args.start,
            duration_seconds=args.duration,
        )


if __name__ == "__main__":
    main()
