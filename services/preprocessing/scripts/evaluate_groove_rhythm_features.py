#!/usr/bin/env python3
"""Validate rhythm-feature decisions on the official Groove MIDI Dataset.

The MIDI performance is the event-level reference and the aligned WAV is sent
through the configured drum transcriber. Both routes use the same annotated
beat/downbeat grid so this benchmark measures the drum-event -> rhythm-feature
chain rather than mixing beat-tracker errors into the result.

No threshold is selected on the official test split. Production thresholds
must already be fixed before this script is run.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import mido
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.benchmark_evaluation import binary_metrics  # noqa: E402
from app.modules.library.rhythm_feature_analysis import analyze_rhythm_features  # noqa: E402
from scripts.evaluate_drum_transcriber import run_worker  # noqa: E402


BENCHMARK_NAME = "Groove MIDI Dataset v1.0.0"
DATASET_SHA256 = "21559feb2f1c96ca53988fd4d7060b1f2afe1d854fb2a8dcea5ff95cf3cce7e9"
OPEN_HAT_PITCHES = {26, 46}
# GMD was recorded from a Roland TD-11 and its official mapping contains
# edge/bow articulations outside the reduced five-class/General-MIDI map.
GMD_MIDI_FAMILY = {
    36: "kick",
    **{pitch: "snare" for pitch in (37, 38, 40)},
    **{pitch: "hihat" for pitch in (22, 26, 42, 44, 46)},
    **{pitch: "tom" for pitch in (43, 45, 47, 48, 50, 58)},
    **{pitch: "cymbal" for pitch in (49, 51, 52, 53, 55, 57, 59)},
}
FEATURE_RELEASE_EXCLUSIONS = {
    # ADTOF's five-class channel is GM42 and cannot distinguish open/closed.
    "offbeat_open_hat": "worker_does_not_preserve_open_hat_identity",
    # Repetition + quantization is not a ground-truth drum-machine identity.
    "drum_machine_consistency": "dataset_has_no_drum_machine_identity_annotation",
    # The current score is a dense/tresillo hat proxy, not an annotated Drill
    # performance label. Reproducing the proxy does not validate the name.
    "drill_hat": "dataset_has_no_human_drill_hat_annotation",
}


def _stable_order(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: hashlib.sha256(row["id"].encode()).hexdigest())


def read_midi_reference(path: Path) -> tuple[dict[str, list[dict[str, Any]]], list[float], list[float]]:
    """Read aligned drum events, beats and bars using the complete tempo map."""
    midi = mido.MidiFile(path)
    absolute_tick = 0
    raw_events: list[tuple[int, int, int]] = []
    tempo_events = [(0, 500_000)]
    signature_events = [(0, 4, 4)]
    for message in mido.merge_tracks(midi.tracks):
        absolute_tick += int(message.time)
        if message.type == "set_tempo":
            tempo_events.append((absolute_tick, int(message.tempo)))
        elif message.type == "time_signature":
            signature_events.append(
                (absolute_tick, int(message.numerator), int(message.denominator))
            )
        elif message.type == "note_on" and message.velocity > 0:
            raw_events.append((absolute_tick, int(message.note), int(message.velocity)))
    total_ticks = absolute_tick
    tempo_map = sorted(dict(tempo_events).items())

    def seconds_at(target_tick: float) -> float:
        elapsed = 0.0
        previous_tick = 0.0
        tempo = 500_000
        for event_tick, event_tempo in tempo_map:
            if event_tick > target_tick:
                break
            elapsed += mido.tick2second(
                event_tick - previous_tick, midi.ticks_per_beat, tempo,
            )
            previous_tick = float(event_tick)
            tempo = int(event_tempo)
        return float(elapsed + mido.tick2second(
            target_tick - previous_tick, midi.ticks_per_beat, tempo,
        ))

    events = {family: [] for family in sorted(set(GMD_MIDI_FAMILY.values()))}
    for tick, pitch, velocity in raw_events:
        family = GMD_MIDI_FAMILY.get(pitch)
        if family is None:
            continue
        events[family].append({
            "time": round(seconds_at(tick), 6),
            "midi_pitch": pitch,
            "subtype": "open_hihat" if pitch in OPEN_HAT_PITCHES else f"gm_{pitch}",
            "velocity": velocity,
            "relative_intensity": round(velocity / 127.0, 6),
            "confidence": 1.0,
        })

    beat_ticks = np.arange(
        0, total_ticks + midi.ticks_per_beat, midi.ticks_per_beat, dtype=float,
    )
    beat_points = [seconds_at(tick) for tick in beat_ticks]
    signatures = sorted(dict(
        (tick, (numerator, denominator))
        for tick, numerator, denominator in signature_events
    ).items())
    downbeat_ticks: list[float] = []
    for index, (start_tick, (numerator, denominator)) in enumerate(signatures):
        end_tick = signatures[index + 1][0] if index + 1 < len(signatures) else total_ticks + 1
        bar_ticks = midi.ticks_per_beat * 4.0 / denominator * numerator
        if bar_ticks <= 0:
            continue
        tick = float(start_tick)
        while tick < end_tick and tick <= total_ticks:
            downbeat_ticks.append(tick)
            tick += bar_ticks
    downbeats = [seconds_at(tick) for tick in sorted(set(downbeat_ticks))]
    return events, beat_points, downbeats


def _feature_gate(metrics: dict[str, Any], *, available_fraction: float) -> dict[str, Any]:
    reasons = []
    if metrics["sample_count"] < 50:
        reasons.append("fewer_than_50_available_test_tracks")
    if metrics["positive_count"] < 10:
        reasons.append("fewer_than_10_positive_examples")
    if metrics["negative_count"] < 10:
        reasons.append("fewer_than_10_negative_examples")
    if metrics["accuracy"] < 0.80:
        reasons.append("accuracy_below_0_80")
    if metrics["precision"] < 0.80:
        reasons.append("precision_below_0_80")
    if metrics["recall"] < 0.70:
        reasons.append("recall_below_0_70")
    if metrics["f1"] < 0.80:
        reasons.append("f1_below_0_80")
    if available_fraction < 0.80:
        reasons.append("prediction_coverage_below_0_80")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "thresholds": {
            "minimum_tracks": 50,
            "minimum_positive_examples": 10,
            "minimum_negative_examples": 10,
            "minimum_accuracy": 0.80,
            "minimum_precision": 0.80,
            "minimum_recall": 0.70,
            "minimum_f1": 0.80,
            "minimum_prediction_coverage": 0.80,
        },
    }


def summarize_feature_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    names = sorted(set().union(*(row["reference"] for row in rows))) if rows else []
    result = {}
    for name in names:
        exclusion = FEATURE_RELEASE_EXCLUSIONS.get(name)
        pairs = []
        absolute_errors = []
        unavailable = 0
        for row in rows:
            reference = row["reference"].get(name) or {}
            prediction = row["prediction"].get(name) or {}
            if (
                reference.get("availability") != "available"
                or prediction.get("availability") != "available"
                or reference.get("detected") is None
                or prediction.get("detected") is None
            ):
                unavailable += 1
                continue
            pairs.append((bool(reference["detected"]), bool(prediction["detected"])))
            absolute_errors.append(abs(float(reference["score"]) - float(prediction["score"])))
        metrics = binary_metrics(
            (expected for expected, _ in pairs),
            (predicted for _, predicted in pairs),
        )
        available_fraction = len(pairs) / max(1, len(rows))
        gate = _feature_gate(metrics, available_fraction=available_fraction)
        if exclusion:
            gate = {**gate, "passed": False, "reasons": [exclusion, *gate["reasons"]]}
        result[name] = {
            "metrics": metrics,
            "available_tracks": len(pairs),
            "unavailable_tracks": unavailable,
            "available_fraction": round(available_fraction, 4),
            "mean_absolute_score_error": (
                round(float(np.mean(absolute_errors)), 4) if absolute_errors else None
            ),
            "within_0_20_score_error_fraction": (
                round(float(np.mean(np.asarray(absolute_errors) <= 0.20)), 4)
                if absolute_errors else None
            ),
            "release_gate": gate,
        }
    return result


def evaluate_dataset(
    root: Path,
    command_template: str,
    *,
    split: str = "test",
    limit: int | None = None,
    timeout_seconds: float = 300.0,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    rows = list(csv.DictReader((root / "info.csv").open(encoding="utf-8")))
    if split not in {"validation", "test"}:
        raise ValueError(f"unsupported official split: {split}")
    rows = [
        row for row in rows
        if row.get("split") == split
        and row.get("beat_type") == "beat"
        and row.get("time_signature") == "4-4"
        and row.get("audio_filename")
    ]
    rows = _stable_order(rows)
    if limit is not None:
        rows = rows[:max(0, limit)]
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)

    evaluated = []
    worker_metadata: dict[str, Any] = {}
    for index, row in enumerate(rows, start=1):
        audio_path = root / row["audio_filename"]
        midi_path = root / row["midi_filename"]
        if not audio_path.is_file() or not midi_path.is_file():
            raise FileNotFoundError(f"missing aligned pair for {row['id']}")
        events, beats, downbeats = read_midi_reference(midi_path)
        cache_path = (
            cache_dir / f"{hashlib.sha256(row['id'].encode()).hexdigest()}.json"
            if cache_dir else None
        )
        if cache_path and cache_path.is_file():
            prediction_payload = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            prediction_payload = run_worker(
                command_template, audio_path, timeout=timeout_seconds,
            )
            if cache_path:
                cache_path.write_text(
                    json.dumps(prediction_payload, ensure_ascii=False), encoding="utf-8",
                )
        duration = float(row["duration"])
        bpm = float(row["bpm"])
        reference = analyze_rhythm_features(
            {
                "detector_mode": "annotated_midi",
                "confidence": {"overall": 1.0},
                "events": events,
                "model_validation": {"classes": {
                    name: {"validated": True}
                    for name in ("kick", "snare", "hihat", "tom", "high_percussion")
                }},
            },
            bpm=bpm, beat_points=beats, downbeats=downbeats, duration=duration,
        )
        prediction = analyze_rhythm_features(
            {
                "detector_mode": "dedicated_model",
                "confidence": {"overall": 0.80},
                "events": prediction_payload["events"],
                "model_validation": {"classes": {
                    "kick": {"validated": True},
                    "high_percussion": {"validated": True},
                }},
            },
            bpm=bpm, beat_points=beats, downbeats=downbeats, duration=duration,
        )
        evaluated.append({
            "id": row["id"],
            "style": row["style"],
            "bpm": bpm,
            "duration": duration,
            "reference": reference["features"],
            "prediction": prediction["features"],
        })
        worker_metadata = {
            key: prediction_payload.get(key)
            for key in ("engine", "model_name", "model_version", "thresholds", "limitations")
        }
        print(f"[{index}/{len(rows)}] {row['id']}", file=sys.stderr, flush=True)

    return {
        "benchmark": BENCHMARK_NAME,
        "dataset_license": "CC BY 4.0",
        "official_archive_sha256": DATASET_SHA256,
        "split": f"official_{split}",
        "selection": "paired_audio,beat_type=beat,time_signature=4-4,sha256(id)_order",
        "track_count": len(evaluated),
        "worker": worker_metadata,
        "isolation_rule": "annotated beat/downbeat grid shared by reference and prediction",
        "feature_metrics": summarize_feature_rows(evaluated),
        "tracks": evaluated,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--split", choices=("validation", "test"), default="test")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_dataset(
        args.dataset_root,
        args.command,
        split=args.split,
        limit=args.limit,
        timeout_seconds=args.timeout_seconds,
        cache_dir=args.cache_dir,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
