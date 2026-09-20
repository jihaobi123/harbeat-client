#!/usr/bin/env python3
"""Held-out validation of vocal activity and whole-song vocal density.

Expected corpus layout is the public Jamendo Singing Voice Detection Corpus:
``audio/``, ``labels/`` and the official ``filelists/{train,valid,test}``.
Only ``valid`` selects the frame decision threshold and Platt calibration.
The official ``test`` split is the primary blind result; ``train`` is treated
as a larger secondary held-out split because this evaluator never fits on it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable

import numpy as np
from sklearn.linear_model import LogisticRegression


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.benchmark_evaluation import binary_metrics  # noqa: E402
from scripts.essentia_vocal_activity_worker import (  # noqa: E402
    PATCH_HOP_SECONDS,
    PATCH_WINDOW_SECONDS,
    analyze,
)


def read_annotations(path: Path) -> list[tuple[float, float, bool]]:
    segments = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        start, end, label = float(parts[0]), float(parts[1]), parts[2]
        if end > start:
            segments.append((start, end, label == "sing"))
    return segments


def labels_at_centers(
    frame_count: int, segments: list[tuple[float, float, bool]],
) -> np.ndarray:
    centers = PATCH_WINDOW_SECONDS / 2.0 + np.arange(frame_count) * PATCH_HOP_SECONDS
    return np.asarray([
        next((active for start, end, active in segments if start <= time < end), False)
        for time in centers
    ], dtype=bool)


def reference_density(segments: list[tuple[float, float, bool]]) -> float:
    duration = max((end for _, end, _ in segments), default=0.0)
    active = sum(end - start for start, end, value in segments if value)
    return active / max(duration, 1e-12)


def evaluate_rows(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    metrics = binary_metrics(
        np.concatenate([np.asarray(row["labels"], dtype=bool) for row in rows]),
        np.concatenate([
            np.asarray(row["raw_probabilities"], dtype=float) >= threshold for row in rows
        ]),
    )
    return {
        **metrics,
        "track_count": len(rows),
        "frame_count": sum(len(row["labels"]) for row in rows),
    }


def fit_validation_calibration(rows: list[dict[str, Any]]) -> tuple[float, float]:
    raw = np.concatenate([np.asarray(row["raw_probabilities"], dtype=float) for row in rows])
    labels = np.concatenate([np.asarray(row["labels"], dtype=int) for row in rows])
    model = LogisticRegression(C=1.0, solver="lbfgs").fit(raw[:, None], labels)
    return float(model.coef_[0, 0]), float(model.intercept_[0])


def density_metrics(
    rows: list[dict[str, Any]], *, coefficient: float, intercept: float,
) -> dict[str, Any]:
    errors = []
    song_rows = []
    for row in rows:
        raw = np.asarray(row["raw_probabilities"], dtype=float)
        calibrated = 1.0 / (1.0 + np.exp(-np.clip(coefficient * raw + intercept, -40, 40)))
        predicted = float(np.mean(calibrated)) if len(calibrated) else 0.0
        expected = float(row["reference_density"])
        error = abs(predicted - expected)
        errors.append(error)
        song_rows.append({
            "track": row["track"],
            "reference_density": round(expected, 6),
            "predicted_density": round(predicted, 6),
            "absolute_error": round(error, 6),
        })
    values = np.asarray(errors, dtype=float)
    return {
        "track_count": len(rows),
        "mean_absolute_error": round(float(np.mean(values)), 4),
        "median_absolute_error": round(float(np.median(values)), 4),
        "within_0_10_fraction": round(float(np.mean(values <= 0.10)), 4),
        "within_0_15_fraction": round(float(np.mean(values <= 0.15)), 4),
        "within_0_20_fraction": round(float(np.mean(values <= 0.20)), 4),
        "songs": song_rows,
    }


def choose_threshold(rows: list[dict[str, Any]]) -> float:
    best: tuple[tuple[float, float], float] | None = None
    for threshold in np.arange(0.05, 0.951, 0.01):
        metrics = evaluate_rows(rows, float(threshold))
        key = (
            min(float(metrics[name]) for name in ("accuracy", "precision", "recall", "f1")),
            float(metrics["f1"]),
        )
        if best is None or key > best[0]:
            best = (key, float(threshold))
    assert best is not None
    return best[1]


def load_split(
    dataset_root: Path,
    split: str,
    *,
    embedding_model_path: Path,
    classifier_model_path: Path,
    analyser: Callable[..., dict[str, Any]] = analyze,
) -> list[dict[str, Any]]:
    rows = []
    names = (dataset_root / "filelists" / split).read_text(encoding="utf-8").splitlines()
    for index, name in enumerate(names, start=1):
        result = analyser(
            dataset_root / "audio" / name,
            embedding_model_path=embedding_model_path,
            classifier_model_path=classifier_model_path,
            include_frames=True,
        )
        raw = [float(frame["voice_probability_raw"]) for frame in result["frames"]]
        segments = read_annotations(dataset_root / "labels" / f"{Path(name).stem}.lab")
        rows.append({
            "track": name,
            "raw_probabilities": raw,
            "labels": labels_at_centers(len(raw), segments).tolist(),
            "reference_density": reference_density(segments),
        })
        print(f"[{split} {index}/{len(names)}] {name}", file=sys.stderr)
    return rows


def evaluate_dataset(
    dataset_root: Path,
    *,
    embedding_model_path: Path,
    classifier_model_path: Path,
    analyser: Callable[..., dict[str, Any]] = analyze,
) -> dict[str, Any]:
    rows = {
        split: load_split(
            dataset_root,
            split,
            embedding_model_path=embedding_model_path,
            classifier_model_path=classifier_model_path,
            analyser=analyser,
        )
        for split in ("valid", "test", "train")
    }
    threshold = choose_threshold(rows["valid"])
    coefficient, intercept = fit_validation_calibration(rows["valid"])
    splits = {
        split: {
            "frame_metrics": evaluate_rows(values, threshold),
            "density_metrics": density_metrics(
                values, coefficient=coefficient, intercept=intercept,
            ),
        }
        for split, values in rows.items()
    }
    test_frames = splits["test"]["frame_metrics"]
    test_density = splits["test"]["density_metrics"]
    secondary_frames = splits["train"]["frame_metrics"]
    secondary_density = splits["train"]["density_metrics"]
    frame_names = ("accuracy", "precision", "recall", "f1")
    reasons = [
        f"test_{name}_below_0_80" for name in frame_names
        if float(test_frames[name]) < 0.80
    ]
    if float(test_density["within_0_15_fraction"]) < 0.80:
        reasons.append("test_density_within_0_15_below_0_80")
    for name in frame_names:
        if float(secondary_frames[name]) < 0.80:
            reasons.append(f"secondary_{name}_below_0_80")
    if float(secondary_density["within_0_15_fraction"]) < 0.80:
        reasons.append("secondary_density_within_0_15_below_0_80")
    return {
        "benchmark": "Jamendo Corpus for Singing Voice Detection",
        "source": "https://zenodo.org/records/2585988",
        "feature": "vocal_delivery.vocal_density",
        "protocol": {
            "calibration_split": "official valid (16 tracks)",
            "primary_heldout_split": "official test (16 tracks)",
            "secondary_heldout_split": "official train (61 tracks; never fitted)",
            "frame_reference": "manual sing/nosing label at model-patch center",
            "density_reference": "manual singing duration / annotated duration",
            "density_acceptance_tolerance": 0.15,
        },
        "selected_threshold": round(threshold, 4),
        "platt_calibration": {
            "coefficient": coefficient,
            "intercept": intercept,
        },
        "splits": splits,
        "release_gate": {
            "passed": not reasons,
            "minimum_frame_accuracy_precision_recall_f1": 0.80,
            "minimum_density_within_0_15_fraction": 0.80,
            "reasons": reasons,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--embedding-model", type=Path, required=True)
    parser.add_argument("--classifier-model", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_dataset(
        args.dataset_root,
        embedding_model_path=args.embedding_model,
        classifier_model_path=args.classifier_model,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
