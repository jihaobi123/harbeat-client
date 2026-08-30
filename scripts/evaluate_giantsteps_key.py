#!/usr/bin/env python3
"""Evaluate Harbeat's available key routes on GiantSteps Key annotations."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys

import librosa


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.analysis import (  # noqa: E402
    NOTE_MODE_TO_CAMELOT,
    _analyze_key,
    _analyze_key_essentia,
    _analyze_key_madmom,
    _choose_key_consensus,
    _normalize_note_name,
    _normalize_scale_name,
)


PITCH_CLASS = {name: index for index, name in enumerate(
    ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
)}


def parse_key(value: str) -> tuple[str, str]:
    root_raw, mode_raw = value.strip().rsplit(" ", 1)
    return _normalize_note_name(root_raw), _normalize_scale_name(mode_raw)


def mirex_key_score(reference: tuple[str, str], predicted: tuple[str, str]) -> tuple[str, float]:
    """Standard MIREX key relation score: exact/fifth/relative/parallel."""
    ref_root, ref_mode = reference
    pred_root, pred_mode = predicted
    ref_pc = PITCH_CLASS[ref_root]
    pred_pc = PITCH_CLASS[pred_root]
    interval = (pred_pc - ref_pc) % 12
    if reference == predicted:
        return "exact", 1.0
    if ref_mode == pred_mode and interval == 7:
        return "fifth", 0.5
    if (
        ref_mode == "major" and pred_mode == "minor" and interval == 9
    ) or (
        ref_mode == "minor" and pred_mode == "major" and interval == 3
    ):
        return "relative", 0.3
    if ref_root == pred_root and ref_mode != pred_mode:
        return "parallel", 0.2
    return "other", 0.0


def key_metrics(rows: list[dict], field: str) -> dict:
    relations = []
    scores = []
    for row in rows:
        predicted = row.get(field)
        if not predicted:
            continue
        relation, score = mirex_key_score(tuple(row["reference"]), tuple(predicted))
        relations.append(relation)
        scores.append(score)
    return {
        "sample_count": len(scores),
        "exact_accuracy": round(relations.count("exact") / max(1, len(scores)), 4),
        "mirex_weighted_score": round(sum(scores) / max(1, len(scores)), 4),
        "relations": {name: relations.count(name) for name in ("exact", "fifth", "relative", "parallel", "other")},
    }


def confidence_gated_key_metrics(
    rows: list[dict], field: str, *, threshold: float,
) -> dict:
    accepted = [
        row for row in rows
        if float((row.get("route_confidences") or {}).get(field) or 0.0) >= threshold
    ]
    return {
        **key_metrics(accepted, field),
        "input_sample_count": len(rows),
        "coverage": round(len(accepted) / max(1, len(rows)), 4),
        "confidence_threshold": threshold,
    }


def evaluate(
    dataset_root: Path,
    cache_dir: Path,
    *,
    audio_root: Path | None = None,
    limit: int | None = None,
) -> dict:
    audio_files = sorted((audio_root or (dataset_root / "audio_eval")).glob("*.mp3"))
    if limit is not None:
        audio_files = audio_files[: max(0, limit)]
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, audio_path in enumerate(audio_files, start=1):
        track_id = audio_path.stem
        annotation = dataset_root / "annotations" / "key" / f"{track_id}.key"
        if not annotation.is_file():
            continue
        cache_path = cache_dir / f"{track_id}.json"
        row = (
            json.loads(cache_path.read_text(encoding="utf-8"))
            if cache_path.is_file() else None
        )
        if not row or row.get("version") != "giantsteps_key_route_cache_v2":
            print(f"[{index}/{len(audio_files)}] {track_id}", file=sys.stderr, flush=True)
            y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=120.0)
            routes = {}
            errors = {}
            jobs = {
                "essentia": lambda: _analyze_key_essentia(y, sr, max_duration=120.0),
                "madmom": lambda: _analyze_key_madmom(str(audio_path)),
            }
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(job): name for name, job in jobs.items()}
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        routes[name] = future.result()
                    except Exception as exc:
                        errors[name] = f"{type(exc).__name__}: {exc}"
            local = _analyze_key(y, sr)
            consensus = _choose_key_consensus(routes, errors=errors, local_fallback=local)
            reference = parse_key(annotation.read_text(encoding="utf-8"))
            row = {
                "version": "giantsteps_key_route_cache_v2",
                "track_id": track_id,
                "reference": list(reference),
                "consensus": [consensus["key"].rsplit(" ", 1)[0], consensus["key"].rsplit(" ", 1)[1]],
                "essentia": (
                    list(parse_key(routes["essentia"]["key"])) if "essentia" in routes else None
                ),
                "madmom": (
                    list(parse_key(routes["madmom"]["key"])) if "madmom" in routes else None
                ),
                "local": list(parse_key(local["key"])),
                "route_confidences": {
                    "essentia": round(float((routes.get("essentia") or {}).get("key_confidence") or 0.0), 6),
                    "madmom": round(float((routes.get("madmom") or {}).get("key_confidence") or 0.0), 6),
                    "local": round(float(local.get("key_confidence") or 0.0), 6),
                },
                "decision": consensus["decision"],
                "needs_review": consensus["needs_review"],
                "errors": errors,
                "split": (
                    "calibration"
                    if hashlib.sha256(track_id.encode()).digest()[0] % 2 == 0
                    else "heldout"
                ),
            }
            cache_path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        rows.append(row)
    partitions = {}
    for split in ("calibration", "heldout"):
        selected = [row for row in rows if row["split"] == split]
        partitions[split] = {
            name: key_metrics(selected, name)
            for name in ("consensus", "essentia", "madmom", "local")
        }
    heldout = partitions["heldout"]["consensus"]
    gated_madmom = confidence_gated_key_metrics(rows, "madmom", threshold=0.80)
    return {
        "benchmark": "GiantSteps Key annotations",
        "sample_count": len(rows),
        "metrics": key_metrics(rows, "consensus"),
        "confidence_gated_madmom": gated_madmom,
        "partitions": partitions,
        "release_gate": {
            "partition": "heldout",
            "minimum_samples": 30,
            "minimum_exact_accuracy": 0.80,
            "passed": heldout["sample_count"] >= 30 and heldout["exact_accuracy"] >= 0.80,
        },
        "confidence_gated_release_gate": {
            "minimum_accepted_samples": 30,
            "minimum_exact_accuracy": 0.80,
            "passed": (
                gated_madmom["sample_count"] >= 30
                and gated_madmom["exact_accuracy"] >= 0.80
            ),
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(
        args.dataset_root, args.cache_dir, audio_root=args.audio_root, limit=args.limit,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
