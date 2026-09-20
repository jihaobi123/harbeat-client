#!/usr/bin/env python3
"""Evaluate production beat/downbeat selection on Ballroom annotations."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

import librosa
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.analysis import (  # noqa: E402
    _analyze_downbeats_madmom,
    _analyze_rhythm_parallel,
    _choose_downbeat_consensus,
    _detect_downbeats_with_meter,
    _downbeat_match_metrics,
)


def read_annotations(path: Path) -> tuple[list[float], list[int]]:
    times = []
    positions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        columns = line.split()
        if len(columns) < 2:
            continue
        times.append(float(columns[0]))
        positions.append(int(float(columns[1])))
    return times, positions


def trim_to_annotated_interval(predicted: list[float], reference: list[float]) -> list[float]:
    """Ignore unannotated intros/outros as required by Ballroom's protocol."""
    if not reference:
        return []
    start, end = min(reference), max(reference)
    return [float(value) for value in predicted if start <= float(value) <= end]


def combine_track_metrics(values: list[dict]) -> dict:
    matches = sum(int(item["matches"]) for item in values)
    predicted = sum(int(item["predicted_count"]) for item in values)
    reference = sum(int(item["reference_count"]) for item in values)
    precision = matches / max(1, predicted)
    recall = matches / max(1, reference)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    return {
        "track_count": len(values),
        "reference_count": reference,
        "predicted_count": predicted,
        "matches": matches,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "macro_precision": round(sum(item["precision"] for item in values) / max(1, len(values)), 4),
        "macro_recall": round(sum(item["recall"] for item in values) / max(1, len(values)), 4),
        "macro_f1": round(sum(item["f1"] for item in values) / max(1, len(values)), 4),
    }


def event_metrics(predicted: list[float], reference: list[float], tolerance: float = 0.07) -> dict:
    result = _downbeat_match_metrics(predicted, reference, tolerance=tolerance)
    return {
        **result,
        "predicted_count": len(predicted),
        "reference_count": len(reference),
    }


def evaluate(
    audio_root: Path,
    annotation_root: Path,
    cache_dir: Path,
    *,
    limit: int | None = None,
) -> dict:
    audio_by_id = {path.stem: path for path in audio_root.rglob("*.wav")}
    annotation_files = [
        path for path in annotation_root.glob("*.beats") if path.stem in audio_by_id
    ]
    annotation_files.sort(key=lambda path: hashlib.sha256(path.stem.encode()).digest())
    if limit is not None:
        annotation_files = annotation_files[: max(0, limit)]
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, annotation_path in enumerate(annotation_files, start=1):
        track_id = annotation_path.stem
        audio_path = audio_by_id[track_id]
        reference_beats, positions = read_annotations(annotation_path)
        reference_downbeats = [
            value for value, position in zip(reference_beats, positions, strict=True)
            if position == 1
        ]
        cache_path = cache_dir / f"{track_id}.json"
        prediction = (
            json.loads(cache_path.read_text(encoding="utf-8"))
            if cache_path.is_file() else None
        )
        if not prediction or prediction.get("version") != "ballroom_route_cache_v2":
            print(f"[{index}/{len(annotation_files)}] {track_id}", file=sys.stderr, flush=True)
            y, sr = librosa.load(audio_path, sr=22050, mono=True)
            with ThreadPoolExecutor(max_workers=2) as executor:
                rhythm_future = executor.submit(_analyze_rhythm_parallel, y, sr, max_duration=60.0)
                madmom_future = executor.submit(_analyze_downbeats_madmom, y, sr)
                selected, bpm_consensus, routes = rhythm_future.result()
                try:
                    madmom = madmom_future.result()
                    madmom_error = None
                except Exception as exc:
                    madmom = None
                    madmom_error = f"{type(exc).__name__}: {exc}"
            predicted_beats = [float(value) for value in selected["beat_times"]]
            accent_downbeats, accent_meter = _detect_downbeats_with_meter(
                y, sr, np.asarray(predicted_beats),
            )
            downbeat_routes = {
                name: routes[name]
                for name in ("beat_this", "all_in_one")
                if name in routes and routes[name].get("downbeats")
            }
            if madmom is not None:
                downbeat_routes["madmom"] = madmom
            predicted_downbeats, downbeat_consensus = _choose_downbeat_consensus(
                downbeat_routes,
                accent_fallback=accent_downbeats,
                tolerance=0.07,
                agreement_f1=0.70,
                bpm=float(bpm_consensus["bpm"]),
                beats_per_bar=int(accent_meter.get("numerator", 4) or 4),
                period_tolerance=0.12,
                max_intro_bars=2.0,
            )
            prediction = {
                "version": "ballroom_route_cache_v2",
                "beats": predicted_beats,
                "downbeats": predicted_downbeats,
                "route_beats": {
                    name: [float(value) for value in route.get("beat_times", [])]
                    for name, route in routes.items()
                },
                "route_downbeats": {
                    **{
                        name: [float(value) for value in route.get("downbeats", [])]
                        for name, route in routes.items() if route.get("downbeats")
                    },
                    **(
                        {"madmom": [float(value) for value in madmom.get("downbeats", [])]}
                        if madmom is not None else {}
                    ),
                    "accent_fallback": [float(value) for value in accent_downbeats],
                },
                "selected_beat_engine": selected.get("engine"),
                "bpm": bpm_consensus.get("bpm"),
                "bpm_strategy": bpm_consensus.get("selection_strategy"),
                "predicted_meter": accent_meter.get("numerator"),
                "downbeat_engine": downbeat_consensus.get("selected_engine"),
                "downbeat_status": downbeat_consensus.get("status"),
                "madmom_error": madmom_error,
            }
            cache_path.write_text(json.dumps(prediction, indent=2) + "\n", encoding="utf-8")

        beats = trim_to_annotated_interval(prediction["beats"], reference_beats)
        downbeats = trim_to_annotated_interval(prediction["downbeats"], reference_beats)
        rows.append({
            "track_id": track_id,
            "genre": audio_path.parent.name,
            "split": (
                "calibration"
                if hashlib.sha256(track_id.encode()).digest()[0] % 2 == 0
                else "heldout"
            ),
            "beat_metrics": event_metrics(beats, reference_beats),
            "downbeat_metrics": event_metrics(downbeats, reference_downbeats),
            "route_beat_metrics": {
                name: event_metrics(
                    trim_to_annotated_interval(values, reference_beats), reference_beats,
                )
                for name, values in (prediction.get("route_beats") or {}).items()
            },
            "route_downbeat_metrics": {
                name: event_metrics(
                    trim_to_annotated_interval(values, reference_beats), reference_downbeats,
                )
                for name, values in (prediction.get("route_downbeats") or {}).items()
            },
            "selected_beat_engine": prediction.get("selected_beat_engine"),
            "downbeat_engine": prediction.get("downbeat_engine"),
            "predicted_meter": prediction.get("predicted_meter"),
        })

    partitions = {}
    for split in ("calibration", "heldout"):
        selected_rows = [row for row in rows if row["split"] == split]
        partitions[split] = {
            "beats": combine_track_metrics([row["beat_metrics"] for row in selected_rows]),
            "downbeats": combine_track_metrics([row["downbeat_metrics"] for row in selected_rows]),
            "beat_routes": {
                name: combine_track_metrics([
                    row["route_beat_metrics"][name]
                    for row in selected_rows if name in row["route_beat_metrics"]
                ])
                for name in ("beat_this", "all_in_one", "essentia")
            },
            "downbeat_routes": {
                name: combine_track_metrics([
                    row["route_downbeat_metrics"][name]
                    for row in selected_rows if name in row["route_downbeat_metrics"]
                ])
                for name in ("beat_this", "all_in_one", "madmom", "accent_fallback")
            },
        }
    heldout_beats = partitions["heldout"]["beats"]
    heldout_downbeats = partitions["heldout"]["downbeats"]

    def passes(metrics: dict) -> bool:
        return bool(
            metrics["track_count"] >= 30
            and metrics["precision"] >= 0.80
            and metrics["recall"] >= 0.80
            and metrics["f1"] >= 0.80
            and metrics["macro_precision"] >= 0.80
            and metrics["macro_recall"] >= 0.80
            and metrics["macro_f1"] >= 0.80
        )

    return {
        "benchmark": "Ballroom beat and bar annotations",
        "sample_count": len(rows),
        "matching_tolerance_ms": 70,
        "partitions": partitions,
        "release_gates": {
            "beats": {"partition": "heldout", "passed": passes(heldout_beats)},
            "downbeats": {"partition": "heldout", "passed": passes(heldout_downbeats)},
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--annotation-root", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(
        args.audio_root, args.annotation_root, args.cache_dir, limit=args.limit,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
