#!/usr/bin/env python3
"""Evaluate Harbeat BPM consensus on a local GiantSteps Tempo checkout."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys

import librosa

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.analysis import _analyze_rhythm_parallel, _choose_bpm_consensus  # noqa: E402
from app.modules.library.benchmark_evaluation import tempo_metrics  # noqa: E402


def evaluate(dataset_root: Path, cache_dir: Path, *, limit: int | None = None) -> dict:
    audio_files = sorted((dataset_root / "audio").glob("*.mp3"))
    if limit is not None:
        audio_files = audio_files[: max(0, limit)]
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, audio_path in enumerate(audio_files, start=1):
        track_id = audio_path.name.removesuffix(".mp3")
        annotation_path = dataset_root / "annotations_v2" / "tempo" / f"{track_id}.bpm"
        if not annotation_path.is_file():
            continue
        expected = float(annotation_path.read_text(encoding="utf-8").strip())
        if expected <= 0:
            continue
        cache_path = cache_dir / f"{track_id}.json"
        if cache_path.is_file():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            print(f"[{index}/{len(audio_files)}] {track_id}", file=sys.stderr, flush=True)
            audio, sr = librosa.load(audio_path, sr=22050, mono=True, duration=120.0)
            with redirect_stdout(sys.stderr):
                selected, consensus, routes = _analyze_rhythm_parallel(
                    audio, sr, max_duration=120.0,
                )
            payload = {
                "track_id": track_id,
                "expected_bpm": expected,
                "predicted_bpm": float(consensus["bpm"]),
                "selected_engine": selected.get("engine"),
                "needs_review": bool(consensus.get("needs_review")),
                "metrical_level_conflict": bool(consensus.get("metrical_level_conflict")),
                "route_bpms": {name: value.get("bpm") for name, value in routes.items()},
            }
            cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        # Recompute the decision from cached route measurements so a consensus
        # strategy change can be evaluated without rerunning the three models.
        recomputed = _choose_bpm_consensus({
            name: {"bpm": bpm}
            for name, bpm in (payload.get("route_bpms") or {}).items()
            if bpm is not None
        })
        payload = {
            **payload,
            "predicted_bpm": float(recomputed["bpm"]),
            "selected_engine": recomputed["selected_engine"],
            "needs_review": bool(recomputed["needs_review"]),
            "metrical_level_conflict": bool(recomputed["metrical_level_conflict"]),
            "selection_strategy": recomputed["selection_strategy"],
            "split": (
                "calibration"
                if hashlib.sha256(track_id.encode()).digest()[0] % 2 == 0
                else "heldout"
            ),
        }
        rows.append(payload)
    def metrics_for(selected_rows: list[dict], field: str) -> dict:
        if field == "predicted_bpm":
            predicted = [row[field] for row in selected_rows]
        else:
            predicted = [row["route_bpms"].get(field) for row in selected_rows]
        pairs = [
            (row["expected_bpm"], value)
            for row, value in zip(selected_rows, predicted, strict=True)
            if value is not None
        ]
        return tempo_metrics(
            (reference for reference, _ in pairs),
            (value for _, value in pairs),
        )

    partitions = {}
    for split in ("calibration", "heldout"):
        selected_rows = [row for row in rows if row["split"] == split]
        partitions[split] = {
            "consensus": metrics_for(selected_rows, "predicted_bpm"),
            "routes": {
                name: metrics_for(selected_rows, name)
                for name in ("essentia", "beat_this", "all_in_one")
            },
        }
    metrics = metrics_for(rows, "predicted_bpm")
    heldout = partitions["heldout"]["consensus"]
    return {
        "benchmark": "GiantSteps Tempo annotations_v2",
        "sample_count": len(rows),
        "metrics": metrics,
        "partitions": partitions,
        "release_gate": {
            "minimum_samples": 30,
            "minimum_accuracy_1": 0.80,
            "partition": "heldout",
            "passed": heldout["sample_count"] >= 30 and heldout["accuracy_1"] >= 0.80,
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.dataset_root, args.cache_dir, limit=args.limit)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
