#!/usr/bin/env python3
"""Build automatic validation and a minimal human-review queue for audio features."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.feature_review_artifacts import render_review_clips, render_review_html  # noqa: E402
from app.modules.library.feature_validation import ReviewPolicy, minimize_review_queue, triage_track_features  # noqa: E402
from app.modules.library.stem_analysis import analyze_stem_files  # noqa: E402


AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".aac"}
KPOP_RHYTHM_SELECTION = {
    "I Need U - BTS": "beat_this",
    "Love Shot - EXO": "beat_this",
    "Shut Down - BLACKPINK": "madmom",
}


def separate(input_dir: Path, stem_root: Path, *, model: str, device: str) -> None:
    tracks = sorted(path for path in input_dir.iterdir() if path.suffix.lower() in AUDIO_SUFFIXES)
    for index, track in enumerate(tracks, start=1):
        expected = stem_root / model / track.stem
        if all((expected / f"{name}.wav").is_file() for name in ("vocals", "drums", "bass", "other")):
            print(f"[{index}/{len(tracks)}] {track.name}: stems cached", flush=True)
            continue
        print(f"[{index}/{len(tracks)}] {track.name}: separating", flush=True)
        command = [
            sys.executable, "-m", "demucs", "-n", model, "-d", device,
            "--out", str(stem_root), str(track),
        ]
        subprocess.run(command, cwd=ROOT, check=True)


def _rhythm_payload(track: Path, rhythm_root: Path) -> dict[str, Any]:
    preferred = KPOP_RHYTHM_SELECTION.get(track.stem, "beat_this")
    candidates = [preferred, "beat_this", "all_in_one", "madmom"]
    for engine in dict.fromkeys(candidates):
        path = rhythm_root / track.stem / f"{engine}.json"
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "error" not in payload:
                return payload
    return {"bpm": None, "beat_times": [], "downbeats": [], "engine": "unavailable"}


def build_manifest(input_dir: Path, stem_root: Path, rhythm_root: Path, output_path: Path, *, model: str) -> list[dict]:
    rows = []
    for track in sorted(path for path in input_dir.iterdir() if path.suffix.lower() in AUDIO_SUFFIXES):
        rhythm = _rhythm_payload(track, rhythm_root)
        stem_dir = stem_root / model / track.stem
        stems = {name: str(stem_dir / f"{name}.wav") for name in ("vocals", "drums", "bass", "other")}
        missing = [name for name, path in stems.items() if not Path(path).is_file()]
        rows.append({
            "track_id": track.stem,
            "title": track.stem,
            "source": str(track),
            "stems": stems,
            "missing_stems": missing,
            "duration": rhythm.get("duration_seconds"),
            "bpm": rhythm.get("bpm"),
            "beat_points": rhythm.get("beat_times", []),
            "downbeats": rhythm.get("downbeats", []),
            "rhythm_engine": rhythm.get("engine"),
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def analyze(
    manifest_path: Path,
    output_dir: Path,
    *,
    panns_checkpoint: Path | None,
    max_review_items: int,
) -> dict[str, Any]:
    tracks = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if panns_checkpoint and panns_checkpoint.is_file():
        worker = ROOT / "scripts/panns_audio_tagger.py"
        os.environ["FEATURE_AUDIO_TAGGER_COMMAND"] = (
            f'{sys.executable} "{worker}" --audio "{{audio}}" --checkpoint "{panns_checkpoint}"'
        )
    os.environ.setdefault("FEATURE_ENABLE_BASIC_PITCH", "false")
    track_results = []
    track_assets = {}
    for index, track in enumerate(tracks, start=1):
        output_path = raw_dir / f"{track['track_id']}.json"
        if output_path.is_file():
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            print(f"[{index}/{len(tracks)}] {track['title']}: analysis cached", flush=True)
        else:
            print(f"[{index}/{len(tracks)}] {track['title']}: analyzing", flush=True)
            stem_result = analyze_stem_files(
                track["stems"],
                original_path=track["source"],
                bpm=track.get("bpm"),
                beat_points=track.get("beat_points") or [],
                downbeats=track.get("downbeats") or [],
            )
            duration = float(track.get("duration") or 0.0)
            if duration <= 0:
                duration = max((item.get("end", 0.0) for item in stem_result.get("stem_activity_windows", [])), default=0.0)
            payload = {
                "track": track,
                "stem_quality_score": stem_result.get("stem_quality_score"),
                "drum_analysis": stem_result.get("drum_analysis"),
                "feature_analysis": stem_result.get("feature_analysis"),
                "model_evidence": stem_result.get("model_evidence"),
                "duration": duration,
            }
            output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        track_results.append(triage_track_features(
            track_id=track["track_id"],
            title=track["title"],
            duration=float(payload.get("duration") or track.get("duration") or 0.0),
            feature_analysis=payload["feature_analysis"],
            policy=ReviewPolicy(max_items=max_review_items),
        ))
        track_assets[track["track_id"]] = {"source": track["source"], **track["stems"]}
    policy = ReviewPolicy(max_items=max_review_items)
    queue = minimize_review_queue(track_results, policy=policy)
    rendered = render_review_clips(queue, track_assets, output_dir / "review")
    render_review_html(rendered, output_dir / "review")
    (output_dir / "automatic_validation.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    separate_parser = subparsers.add_parser("separate")
    separate_parser.add_argument("--input-dir", type=Path, required=True)
    separate_parser.add_argument("--stem-root", type=Path, required=True)
    separate_parser.add_argument("--model", default="htdemucs")
    separate_parser.add_argument("--device", default="mps")
    manifest_parser = subparsers.add_parser("manifest")
    manifest_parser.add_argument("--input-dir", type=Path, required=True)
    manifest_parser.add_argument("--stem-root", type=Path, required=True)
    manifest_parser.add_argument("--rhythm-root", type=Path, required=True)
    manifest_parser.add_argument("--output", type=Path, required=True)
    manifest_parser.add_argument("--model", default="htdemucs")
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--manifest", type=Path, required=True)
    analyze_parser.add_argument("--output-dir", type=Path, required=True)
    analyze_parser.add_argument("--panns-checkpoint", type=Path)
    analyze_parser.add_argument("--max-review-items", type=int, default=24)
    args = parser.parse_args()
    if args.command == "separate":
        separate(args.input_dir, args.stem_root, model=args.model, device=args.device)
    elif args.command == "manifest":
        build_manifest(args.input_dir, args.stem_root, args.rhythm_root, args.output, model=args.model)
    else:
        result = analyze(
            args.manifest,
            args.output_dir,
            panns_checkpoint=args.panns_checkpoint,
            max_review_items=max(1, args.max_review_items),
        )
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
