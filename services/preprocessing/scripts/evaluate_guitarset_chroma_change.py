#!/usr/bin/env python3
"""Evaluate the production beat-synchronous chroma change fallback."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import librosa
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.benchmark_evaluation import binary_metrics  # noqa: E402
from app.modules.library.musical_context_feature_analysis import _harmony_features  # noqa: E402
from scripts.evaluate_guitarset_chords import (  # noqa: E402
    _split,
    activity_score,
    change_boundaries,
    find_audio,
    load_reference,
)


def summarize(rows: list[dict]) -> dict:
    expected = np.asarray([row["reference_activity"] for row in rows], dtype=float)
    predicted = np.asarray([row["predicted_activity"] for row in rows], dtype=float)
    errors = np.abs(expected - predicted)
    return {
        "track_count": len(rows),
        "binary_metrics": binary_metrics(expected >= 0.58, predicted >= 0.58),
        "mean_absolute_error": round(float(np.mean(errors)), 4),
        "within_0_20_fraction": round(float(np.mean(errors <= 0.20)), 4),
    }


def evaluate_dataset(annotation_root: Path, audio_root: Path) -> dict:
    paths = sorted(annotation_root.rglob("*_comp.jams"))
    rows = []
    for index, annotation_path in enumerate(paths, start=1):
        reference, beats, measure_count = load_reference(annotation_path)
        audio_path = find_audio(audio_root, annotation_path)
        audio, _ = librosa.load(audio_path, sr=22_050, mono=True)
        features, _ = _harmony_features(audio, 22_050, {}, beats)
        rows.append({
            "track": annotation_path.stem,
            "split": _split(annotation_path.stem),
            "reference_activity": activity_score(
                change_boundaries(reference), measure_count,
            ),
            "predicted_activity": float(features["chord_change_activity"]["score"]),
        })
        print(f"[{index}/{len(paths)}] {annotation_path.stem}", file=sys.stderr)
    splits = {
        split: summarize([row for row in rows if row["split"] == split])
        for split in ("calibration", "heldout")
    }
    heldout = splits["heldout"]
    reasons = [
        f"heldout_{name}_below_0_80"
        for name in ("accuracy", "precision", "recall", "f1")
        if float(heldout["binary_metrics"][name]) < 0.80
    ]
    if float(heldout["within_0_20_fraction"]) < 0.80:
        reasons.append("heldout_within_0_20_below_0_80")
    return {
        "benchmark": "GuitarSet accompaniment recordings",
        "feature": "harmony.chord_change_activity",
        "method": "beat_synchronous_chroma_harmony_v4",
        "validation_scope": "audio_to_continuous_change_activity_without_chord_labels",
        "splits": splits,
        "release_gate": {
            "passed": not reasons,
            "minimum_accuracy_precision_recall_f1": 0.80,
            "minimum_within_0_20_fraction": 0.80,
            "reasons": reasons,
        },
        "tracks": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotation-root", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_dataset(args.annotation_root, args.audio_root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
