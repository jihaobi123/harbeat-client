#!/usr/bin/env python3
"""Evaluate frozen candidates once on a new, untouched labelled split."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.section_relabeler import STRUCTURE_LABELS
from app.modules.library.section_structure_context import structure_context_is_complete
from scripts.train_section_relabeler import collect_rows, gated_predictions, metrics
from scripts.train_section_relabeler_candidates import (
    SCHEMA_VERSION,
    align_cache,
    candidate_matrices,
    load_feature_cache,
    sha256_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--audio-cache", type=Path)
    parser.add_argument("--stem-cache", type=Path)
    return parser.parse_args()


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    values = np.exp(shifted)
    return values / np.sum(values, axis=1, keepdims=True)


def predict(model: dict[str, Any], x: np.ndarray, originals: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    parameters = model["parameters"]
    mean = np.asarray(parameters["feature_mean"], dtype=np.float64)
    scale = np.asarray(parameters["feature_scale"], dtype=np.float64)
    coefficients = np.asarray(parameters["coefficients"], dtype=np.float64)
    intercept = np.asarray(parameters["intercept"], dtype=np.float64)
    labels = [str(value) for value in parameters["labels"]]
    if x.shape[1] != len(mean) or coefficients.shape != (len(labels), len(mean)):
        raise ValueError(f"model/input dimension mismatch for {model['candidate_id']}")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        logits = np.einsum(
            "ij,kj->ik", (x - mean) / scale, coefficients, optimize=False
        ) + intercept
    if not np.all(np.isfinite(logits)):
        raise ValueError(f"non-finite classifier scores for {model['candidate_id']}")
    probabilities = _softmax(logits)
    final, proposed = gated_predictions(
        probabilities, labels, originals, float(parameters["override_threshold"])
    )
    confidence = np.max(probabilities, axis=1)
    return final, proposed, confidence


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite an existing blind-test result: {args.output}")
    dataset_path = args.dataset.resolve()
    candidate_dir = args.candidate_dir.resolve()
    manifest = json.loads((candidate_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit("unsupported candidate manifest")
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    base, y, originals, groups, records = collect_rows(
        payload, args.split, include_low_confidence=False
    )
    if not len(y):
        raise SystemExit(f"no trainable labelled rows in split {args.split!r}")
    overlap = sorted(set(groups.tolist()) & set(manifest.get("known_track_ids") or []))
    if overlap:
        raise SystemExit(
            f"blind-test leakage guard: {len(overlap)} track IDs were used during development; first={overlap[0]}"
        )

    audio_lookup: dict[tuple[str, int], np.ndarray] = {}
    stem_lookup: dict[tuple[str, int], np.ndarray] = {}
    audio_dimensions = stem_dimensions = 0
    if args.audio_cache:
        audio_lookup, audio_dimensions = load_feature_cache(args.audio_cache.resolve())
    if args.stem_cache:
        stem_lookup, stem_dimensions = load_feature_cache(args.stem_cache.resolve())
    audio = (
        align_cache(records, audio_lookup, audio_dimensions, "mixed-audio cache")
        if audio_lookup
        else np.zeros((len(y), 0), dtype=np.float64)
    )
    stems = (
        align_cache(records, stem_lookup, stem_dimensions, "stem cache")
        if stem_lookup
        else np.zeros((len(y), 0), dtype=np.float64)
    )
    available = {
        candidate_id: {"feature_names": names, "matrix": x}
        for candidate_id, _, _, names, x in candidate_matrices(base, audio, stems)
    }
    segment_lookup = {
        (str(track["track_id"]), int(segment.get("segment_index", index))): segment
        for track in payload.get("tracks") or []
        if track.get("split") == args.split
        for index, segment in enumerate(track.get("segments") or [])
    }
    results: list[dict[str, Any]] = []
    for entry in manifest["models"]:
        model_path = candidate_dir / entry["model_path"]
        if sha256_file(model_path) != entry["model_sha256"]:
            raise SystemExit(f"frozen model hash mismatch: {model_path}")
        model = json.loads(model_path.read_text(encoding="utf-8"))
        components = set(model["input_contract"]["components"])
        if "mixed_audio_dsp" in components and not args.audio_cache:
            results.append({"candidate_id": model["candidate_id"], "status": "skipped_missing_audio_cache"})
            continue
        if "demucs_stems" in components and not args.stem_cache:
            results.append({"candidate_id": model["candidate_id"], "status": "skipped_missing_stem_cache"})
            continue
        if components & {"whole_song_structure", "encoder_projection"}:
            incomplete = [
                record for record in records
                if not structure_context_is_complete(
                    segment_lookup[(str(record["track_id"]), int(record["segment_index"]))]
                )
            ]
            if incomplete:
                results.append({
                    "candidate_id": model["candidate_id"],
                    "status": "skipped_missing_structure_context",
                    "missing_segments": len(incomplete),
                })
                continue
        candidate = available[model["candidate_id"]]
        if candidate["feature_names"] != model["input_contract"]["feature_names"]:
            raise SystemExit(f"feature-name contract mismatch: {model['candidate_id']}")
        x = candidate["matrix"]
        final, proposed, confidence = predict(model, x, originals)
        result = metrics(y, final, originals)
        ungated = metrics(y, proposed, originals)
        result.update({
            "candidate_id": model["candidate_id"],
            "model_version": model["model_version"],
            "status": "evaluated",
            "ungated_classifier": ungated,
            "predictions": [
                {
                    **record,
                    "proposed": str(proposed[index]),
                    "final": str(final[index]),
                    "confidence": float(confidence[index]),
                    "correct": bool(final[index] == y[index]),
                }
                for index, record in enumerate(records)
            ],
        })
        results.append(result)
    evaluated = [item for item in results if item["status"] == "evaluated"]
    ranking = sorted(
        (
            {
                "candidate_id": item["candidate_id"],
                "accuracy": item["accuracy"],
                "macro_f1": item["macro_f1"],
                "fixed_errors": item["fixed_errors"],
                "introduced_errors": item["introduced_errors"],
            }
            for item in evaluated
        ),
        key=lambda item: (item["accuracy"], item["macro_f1"], -item["introduced_errors"]),
        reverse=True,
    )
    output = {
        "schema_version": "harbeat_section_blind_evaluation_v1",
        "candidate_manifest_sha256": sha256_file(candidate_dir / "manifest.json"),
        "test_dataset": str(dataset_path),
        "test_dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "split": args.split,
        "segments": int(len(y)),
        "independent_tracks": int(len(set(groups.tolist()))),
        "baseline_accuracy": float(np.mean(y == originals)),
        "labels": list(STRUCTURE_LABELS),
        "ranking": ranking,
        "results": results,
        "selection_rule": "highest blind accuracy, then macro-F1, then fewer introduced errors; inspect confidence intervals before production selection",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "ranking": ranking}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
