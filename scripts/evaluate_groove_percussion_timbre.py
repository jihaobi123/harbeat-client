#!/usr/bin/env python3
"""Audit fixed percussion-timbre rules on held-out GMD drum audio.

This is intentionally a favourable test: it uses exact MIDI onset times and
only isolated hits. A rule that fails here must not be promoted when its onset
would come from an imperfect audio transcriber in production.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import librosa


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.benchmark_evaluation import binary_metrics  # noqa: E402
from app.modules.library.percussion_feature_analysis import (  # noqa: E402
    _descriptor,
    matches_percussion_family,
)
from scripts.evaluate_groove_rhythm_features import read_midi_reference  # noqa: E402


LABELS = {
    "full_snare": ({38, 40}, {37}),
    "short_rim_snap": ({37}, {38, 40}),
    "short_metallic": ({22, 42, 44}, {26, 46, 49, 51, 52, 53, 55, 57, 59}),
    "sustained_metallic": ({26, 46, 49, 51, 52, 53, 55, 57, 59}, {22, 42, 44}),
}


def _gate(metrics: dict[str, Any], *, track_count: int) -> dict[str, Any]:
    reasons = []
    if track_count < 30:
        reasons.append("fewer_than_30_heldout_tracks")
    if metrics["positive_count"] < 50 or metrics["negative_count"] < 50:
        reasons.append("insufficient_balanced_event_support")
    for key in ("accuracy", "precision", "recall", "f1"):
        if float(metrics[key]) < 0.80:
            reasons.append(f"{key}_below_0_80")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "thresholds": {
            "minimum_heldout_tracks": 30,
            "minimum_events_per_class": 50,
            "minimum_accuracy_precision_recall_f1": 0.80,
        },
    }


def evaluate_dataset(
    root: Path,
    *,
    split: str = "test",
    maximum_events_per_pitch_per_track: int = 20,
) -> dict[str, Any]:
    if split not in {"validation", "test"}:
        raise ValueError(f"unsupported official split: {split}")
    rows = list(csv.DictReader((root / "info.csv").open(encoding="utf-8")))
    rows = sorted(
        [
            row for row in rows
            if row.get("split") == split
            and row.get("audio_filename")
            and row.get("beat_type") == "beat"
            and row.get("time_signature") == "4-4"
        ],
        key=lambda row: hashlib.sha256(row["id"].encode()).hexdigest(),
    )
    observations: dict[str, list[tuple[bool, bool]]] = {name: [] for name in LABELS}
    pitch_counts: dict[int, int] = {}
    for index, row in enumerate(rows, start=1):
        audio, sr = librosa.load(root / row["audio_filename"], sr=None, mono=True)
        events, _, _ = read_midi_reference(root / row["midi_filename"])
        ordered = sorted(
            (event for values in events.values() for event in values),
            key=lambda event: event["time"],
        )
        isolated = []
        for event_index, event in enumerate(ordered):
            previous_close = (
                event_index > 0 and event["time"] - ordered[event_index - 1]["time"] < 0.035
            )
            next_close = (
                event_index + 1 < len(ordered)
                and ordered[event_index + 1]["time"] - event["time"] < 0.035
            )
            if not previous_close and not next_close:
                isolated.append(event)
        by_pitch: dict[int, list[dict[str, Any]]] = {}
        for event in isolated:
            by_pitch.setdefault(int(event["midi_pitch"]), []).append(event)
        for pitch, values in by_pitch.items():
            for event in values[:maximum_events_per_pitch_per_track]:
                descriptor = _descriptor(audio, sr, {
                    "time": event["time"],
                    "input_class": "annotated_midi",
                    "input_subtype": f"gmd_{pitch}",
                    "input_confidence": 1.0,
                })
                if descriptor is None:
                    continue
                pitch_counts[pitch] = pitch_counts.get(pitch, 0) + 1
                for name, (positive, negative) in LABELS.items():
                    if pitch not in positive | negative:
                        continue
                    observations[name].append((
                        pitch in positive,
                        matches_percussion_family(name, descriptor),
                    ))
        print(f"[{index}/{len(rows)}] {row['id']}", file=sys.stderr, flush=True)

    features = {}
    for name, values in observations.items():
        positive = [value for value in values if value[0]]
        negative = [value for value in values if not value[0]]
        balanced_count = min(len(positive), len(negative))
        balanced = positive[:balanced_count] + negative[:balanced_count]
        metrics = binary_metrics(
            (expected for expected, _ in balanced),
            (predicted for _, predicted in balanced),
        )
        features[name] = {
            "metrics": metrics,
            "raw_positive_count": len(positive),
            "raw_negative_count": len(negative),
            "release_gate": _gate(metrics, track_count=len(rows)),
        }
    unavailable = sorted(
        set((
            "wide_clap", "low_pitched_drum", "mid_pitched_drum",
            "hand_drum_family", "tonal_percussion", "repeated_tonal_motif",
        ))
    )
    return {
        "benchmark": "Groove MIDI Dataset v1.0.0",
        "dataset_license": "CC BY 4.0",
        "split": f"official_{split}",
        "track_count": len(rows),
        "protocol": "exact_midi_onsets,isolated_hits_35ms,balanced_classes",
        "feature_metrics": features,
        "not_evaluable_from_gmd_labels": unavailable,
        "sampled_event_count_by_midi_pitch": {
            str(key): value for key, value in sorted(pitch_counts.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--split", choices=("validation", "test"), default="test")
    parser.add_argument("--maximum-events-per-pitch-per-track", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_dataset(
        args.dataset_root,
        split=args.split,
        maximum_events_per_pitch_per_track=args.maximum_events_per_pitch_per_track,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
