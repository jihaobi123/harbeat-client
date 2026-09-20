#!/usr/bin/env python3
"""Evaluate madmom chord labels, boundaries and derived change activity.

Only GuitarSet accompaniment (``*_comp``) recordings are used.  Solo takes
follow the same lead sheet but do not necessarily contain sounding chords and
would therefore be invalid negatives for chord recognition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.benchmark_evaluation import binary_metrics  # noqa: E402
from scripts.madmom_chord_worker import ChordRecognizer, recognize  # noqa: E402


def _split(value: str) -> str:
    return "calibration" if hashlib.sha256(value.encode()).digest()[0] % 2 == 0 else "heldout"


def load_reference(path: Path) -> tuple[list[dict[str, Any]], list[float], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    chord_annotations = [
        value for value in payload.get("annotations", []) if value.get("namespace") == "chord"
    ]
    if not chord_annotations:
        raise ValueError(f"missing chord annotation: {path}")
    # The first GuitarSet chord annotation is the simplified chord sequence;
    # the second retains inversions/extensions derived from string notes.
    chords = [
        {
            "start": float(value["time"]),
            "end": float(value["time"]) + float(value["duration"]),
            "label": str(value["value"]),
        }
        for value in chord_annotations[0].get("data", [])
        if float(value.get("duration", 0.0)) > 0
    ]
    beat_annotations = [
        value for value in payload.get("annotations", [])
        if value.get("namespace") == "beat_position"
    ]
    beats = [
        float(value["time"])
        for value in (beat_annotations[0].get("data", []) if beat_annotations else [])
    ]
    measures = {
        int((value.get("value") or {}).get("measure", 0))
        for value in (beat_annotations[0].get("data", []) if beat_annotations else [])
        if int((value.get("value") or {}).get("measure", 0)) > 0
    }
    return chords, beats, len(measures)


def find_audio(audio_root: Path, annotation_path: Path) -> Path:
    candidates = sorted(audio_root.rglob(f"{annotation_path.stem}*.wav"))
    if len(candidates) != 1:
        raise FileNotFoundError(
            f"expected one audio file for {annotation_path.stem}, got {len(candidates)}"
        )
    return candidates[0]


def reduce_chord(label: str) -> str | None:
    value = str(label).split("/", 1)[0]
    if value.upper() in {"N", "X"}:
        return "N"
    if ":" not in value:
        return None
    root, quality = value.split(":", 1)
    if quality in {"maj", "7", "maj7", "maj6"}:
        return f"{root}:maj"
    if quality in {"min", "min7", "min6"}:
        return f"{root}:min"
    # Madmom's published vocabulary cannot represent diminished or
    # half-diminished chords, so those frames are reported as unsupported
    # rather than silently counted as the wrong major/minor class.
    return None


def label_at(time: float, segments: list[dict[str, Any]]) -> str | None:
    for value in segments:
        if float(value["start"]) <= time < float(value["end"]):
            return reduce_chord(str(value["label"]))
    return "N"


def weighted_chord_accuracy(
    reference: list[dict[str, Any]], predicted: list[dict[str, Any]], *, step: float = 0.05,
) -> dict[str, Any]:
    duration = max((float(value["end"]) for value in reference), default=0.0)
    times = np.arange(step / 2.0, duration, step)
    expected = [label_at(float(time), reference) for time in times]
    actual = [label_at(float(time), predicted) for time in times]
    supported = [index for index, value in enumerate(expected) if value is not None]
    correct = sum(expected[index] == actual[index] for index in supported)
    return {
        "supported_duration_seconds": round(len(supported) * step, 4),
        "unsupported_duration_seconds": round((len(times) - len(supported)) * step, 4),
        "major_minor_weighted_accuracy": round(correct / max(len(supported), 1), 4),
    }


def change_boundaries(segments: list[dict[str, Any]]) -> list[float]:
    recognized = [
        value for value in segments if reduce_chord(str(value.get("label"))) not in {None, "N"}
    ]
    return [
        float(right["start"])
        for left, right in zip(recognized[:-1], recognized[1:])
        if reduce_chord(str(left["label"])) != reduce_chord(str(right["label"]))
    ]


def boundary_metrics(
    reference: Iterable[float], predicted: Iterable[float], *, tolerance: float = 0.5,
) -> dict[str, Any]:
    refs, preds = sorted(reference), sorted(predicted)
    candidates = sorted(
        (abs(left - right), i, j)
        for i, left in enumerate(refs)
        for j, right in enumerate(preds)
        if abs(left - right) <= tolerance
    )
    used_refs: set[int] = set()
    used_preds: set[int] = set()
    errors = []
    for error, i, j in candidates:
        if i in used_refs or j in used_preds:
            continue
        used_refs.add(i)
        used_preds.add(j)
        errors.append(error)
    matches = len(errors)
    precision = matches / max(len(preds), 1)
    recall = matches / max(len(refs), 1)
    return {
        "reference_count": len(refs),
        "prediction_count": len(preds),
        "matches": matches,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / max(precision + recall, 1e-12), 4),
        "mean_error_ms": round(float(np.mean(errors)) * 1000.0, 3) if errors else None,
        "tolerance_seconds": tolerance,
    }


def activity_score(boundaries: list[float], measure_count: int) -> float:
    changes_per_bar = len(boundaries) / max(measure_count, 1)
    return float(np.clip(changes_per_bar, 0.0, 1.0))


def predicted_activity_score(boundaries: list[float], measure_count: int) -> float:
    """Apply the calibration-split over-segmentation correction."""
    changes_per_bar = len(boundaries) / max(measure_count, 1)
    return float(np.clip(0.85 * changes_per_bar, 0.0, 1.0))


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    boundary_reference = sum(row["boundary_metrics"]["reference_count"] for row in rows)
    boundary_prediction = sum(row["boundary_metrics"]["prediction_count"] for row in rows)
    boundary_matches = sum(row["boundary_metrics"]["matches"] for row in rows)
    boundary_precision = boundary_matches / max(boundary_prediction, 1)
    boundary_recall = boundary_matches / max(boundary_reference, 1)
    boundary_f1 = 2 * boundary_precision * boundary_recall / max(
        boundary_precision + boundary_recall, 1e-12,
    )
    expected = np.asarray([row["reference_activity"] for row in rows], dtype=float)
    predicted = np.asarray([row["predicted_activity"] for row in rows], dtype=float)
    errors = np.abs(expected - predicted)
    binary = binary_metrics(expected >= 0.58, predicted >= 0.58)
    weighted_duration = sum(row["label_metrics"]["supported_duration_seconds"] for row in rows)
    weighted_correct = sum(
        row["label_metrics"]["major_minor_weighted_accuracy"]
        * row["label_metrics"]["supported_duration_seconds"]
        for row in rows
    )
    return {
        "track_count": len(rows),
        "boundary_metrics": {
            "reference_count": boundary_reference,
            "prediction_count": boundary_prediction,
            "matches": boundary_matches,
            "precision": round(boundary_precision, 4),
            "recall": round(boundary_recall, 4),
            "f1": round(boundary_f1, 4),
            "tolerance_seconds": 0.5,
        },
        "change_activity": {
            **binary,
            "mean_absolute_error": round(float(np.mean(errors)), 4),
            "within_0_20_fraction": round(float(np.mean(errors <= 0.20)), 4),
        },
        "major_minor_weighted_accuracy": round(
            weighted_correct / max(weighted_duration, 1e-12), 4,
        ),
    }


def evaluate_dataset(annotation_root: Path, audio_root: Path) -> dict[str, Any]:
    annotation_paths = sorted(annotation_root.rglob("*_comp.jams"))
    if not annotation_paths:
        raise FileNotFoundError(f"no *_comp.jams below {annotation_root}")
    recognizer = ChordRecognizer()
    rows = []
    for index, annotation_path in enumerate(annotation_paths, start=1):
        audio_path = find_audio(audio_root, annotation_path)
        reference, beats, measure_count = load_reference(annotation_path)
        prediction = recognize(audio_path, recognizer=recognizer)["segments"]
        ref_boundaries = change_boundaries(reference)
        pred_boundaries = change_boundaries(prediction)
        rows.append({
            "track": annotation_path.stem,
            "split": _split(annotation_path.stem),
            "beat_count": len(beats),
            "measure_count": measure_count,
            "reference_activity": activity_score(ref_boundaries, measure_count),
            "predicted_activity": predicted_activity_score(pred_boundaries, measure_count),
            "boundary_metrics": boundary_metrics(ref_boundaries, pred_boundaries),
            "label_metrics": weighted_chord_accuracy(reference, prediction),
        })
        print(f"[{index}/{len(annotation_paths)}] {annotation_path.stem}", file=sys.stderr)
    splits = {
        split: summarize([row for row in rows if row["split"] == split])
        for split in ("calibration", "heldout")
    }
    heldout = splits["heldout"]
    activity = heldout["change_activity"]
    reasons = []
    for name in ("accuracy", "precision", "recall", "f1"):
        if float(activity[name]) < 0.80:
            reasons.append(f"heldout_activity_{name}_below_0_80")
    if float(activity["within_0_20_fraction"]) < 0.80:
        reasons.append("heldout_activity_within_0_20_below_0_80")
    if float(heldout["boundary_metrics"]["f1"]) < 0.80:
        reasons.append("heldout_boundary_f1_below_0_80")
    return {
        "benchmark": "GuitarSet accompaniment recordings",
        "source": "https://zenodo.org/records/3371780",
        "feature": "harmony.chord_change_activity",
        "protocol": {
            "audio_subset": "*_comp mono microphone recordings",
            "hash_split": "SHA256 filename byte 0 parity",
            "boundary_tolerance_seconds": 0.5,
            "activity_definition": "reference=clip(changes/measures,0,1); prediction=clip(0.85*changes/measures,0,1)",
            "oversegmentation_correction": {
                "factor": 0.85,
                "selected_on": "hash calibration split only",
            },
            "binary_activity_threshold": 0.58,
            "chord_vocabulary": "major/minor/no-chord; unsupported diminished frames excluded",
        },
        "splits": splits,
        "release_gate": {
            "passed": not reasons,
            "minimum_accuracy_precision_recall_f1": 0.80,
            "minimum_activity_within_0_20_fraction": 0.80,
            "minimum_boundary_f1": 0.80,
            "reasons": reasons,
        },
        "claim_limit": (
            "release applies only to high/low change activity; chord labels and exact boundary "
            "precision remain separately reported"
        ),
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
