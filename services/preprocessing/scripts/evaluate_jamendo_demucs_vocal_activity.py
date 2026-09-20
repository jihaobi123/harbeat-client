#!/usr/bin/env python3
"""Audit the legacy Demucs-vocal-stem RMS gate on Jamendo annotations.

This evaluator reproduces the activity gate used by
``musical_context_feature_analysis._vocal_features``.  It exists to compare
the old fallback with the validated full-mix model; it does not tune the gate
on the test data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import librosa
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.benchmark_evaluation import binary_metrics  # noqa: E402
from scripts.evaluate_jamendo_vocal_activity import (  # noqa: E402
    read_annotations,
    reference_density,
)


SAMPLE_RATE = 22_050
FRAME_LENGTH = 1024
HOP_LENGTH = 256


def legacy_activity(audio: np.ndarray) -> tuple[np.ndarray, float]:
    rms = librosa.feature.rms(
        y=np.asarray(audio, dtype=float), frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH,
    )[0]
    low_rms = float(np.percentile(rms, 20))
    high_rms = float(np.percentile(rms, 95))
    gate = max(min(low_rms * 3.0, high_rms * 0.20), high_rms * 0.06, 1e-7)
    return rms >= gate, gate


def labels_at_times(
    times: np.ndarray, segments: list[tuple[float, float, bool]],
) -> np.ndarray:
    return np.asarray([
        next((active for start, end, active in segments if start <= time < end), False)
        for time in times
    ], dtype=bool)


def evaluate_split(
    dataset_root: Path, stem_root: Path, split: str,
) -> dict[str, Any]:
    references = []
    predictions = []
    songs = []
    names = (dataset_root / "filelists" / split).read_text(encoding="utf-8").splitlines()
    for index, name in enumerate(names, start=1):
        stem_path = stem_root / Path(name).stem / "vocals.wav"
        if not stem_path.is_file():
            raise FileNotFoundError(stem_path)
        audio, _ = librosa.load(stem_path, sr=SAMPLE_RATE, mono=True)
        active, gate = legacy_activity(audio)
        times = np.arange(len(active), dtype=float) * HOP_LENGTH / SAMPLE_RATE
        segments = read_annotations(dataset_root / "labels" / f"{Path(name).stem}.lab")
        labels = labels_at_times(times, segments)
        references.extend(labels.tolist())
        predictions.extend(active.tolist())
        expected_density = reference_density(segments)
        predicted_density = float(np.mean(active))
        songs.append({
            "track": name,
            "reference_density": round(expected_density, 6),
            "predicted_density": round(predicted_density, 6),
            "absolute_error": round(abs(predicted_density - expected_density), 6),
            "rms_gate": gate,
        })
        print(f"[{split} {index}/{len(names)}] {name}", file=sys.stderr)
    metrics = binary_metrics(references, predictions)
    errors = np.asarray([row["absolute_error"] for row in songs], dtype=float)
    return {
        "frame_metrics": {
            **metrics,
            "track_count": len(names),
            "frame_count": len(references),
        },
        "density_metrics": {
            "track_count": len(names),
            "mean_absolute_error": round(float(np.mean(errors)), 4),
            "median_absolute_error": round(float(np.median(errors)), 4),
            "within_0_10_fraction": round(float(np.mean(errors <= 0.10)), 4),
            "within_0_15_fraction": round(float(np.mean(errors <= 0.15)), 4),
            "within_0_20_fraction": round(float(np.mean(errors <= 0.20)), 4),
            "songs": songs,
        },
    }


def evaluate_dataset(dataset_root: Path, stem_root: Path) -> dict[str, Any]:
    splits = {
        split: evaluate_split(dataset_root, stem_root, split)
        for split in ("valid", "test")
    }
    test_frames = splits["test"]["frame_metrics"]
    reasons = [
        f"test_{name}_below_0_80"
        for name in ("accuracy", "precision", "recall", "f1")
        if float(test_frames[name]) < 0.80
    ]
    if float(splits["test"]["density_metrics"]["within_0_15_fraction"]) < 0.80:
        reasons.append("test_density_within_0_15_below_0_80")
    return {
        "benchmark": "Jamendo Corpus for Singing Voice Detection",
        "feature": "demucs_vocal_stem_rms_activity",
        "protocol": "vocal_activity_pitch_rhythm_v5_RMS_gate_without_test_tuning",
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
    parser.add_argument("--stem-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_dataset(args.dataset_root, args.stem_root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
