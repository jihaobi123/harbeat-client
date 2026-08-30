#!/usr/bin/env python3
"""Evaluate a JSON drum worker on an annotated MIDI/audio dataset."""
from __future__ import annotations

import argparse
import csv
import json
import hashlib
from pathlib import Path
import subprocess
from typing import Any

import mido

from app.modules.library.benchmark_evaluation import (
    event_release_gate,
    onset_event_metrics,
)
from app.shared.command_line import split_command_line


MIDI_FAMILY = {
    **{pitch: "kick" for pitch in (35, 36)},
    **{pitch: "snare" for pitch in (37, 38, 40)},
    **{pitch: "tom" for pitch in (41, 43, 45, 47, 48, 50)},
    **{pitch: "hihat" for pitch in (42, 44, 46)},
    **{pitch: "cymbal" for pitch in (49, 51, 52, 53, 54, 55, 57, 59)},
}


def merged_event_family(
    events: dict[str, list[Any]], families: tuple[str, ...],
) -> dict[str, list[Any]]:
    return {"merged": [value for family in families for value in events.get(family, [])]}


def read_reference_midi(path: Path) -> tuple[dict[str, list[float]], dict[int, int]]:
    midi = mido.MidiFile(path)
    tempo = 500_000
    elapsed = 0.0
    events = {family: [] for family in sorted(set(MIDI_FAMILY.values()))}
    ignored: dict[int, int] = {}
    for message in mido.merge_tracks(midi.tracks):
        elapsed += mido.tick2second(message.time, midi.ticks_per_beat, tempo)
        if message.type == "set_tempo":
            tempo = message.tempo
        if message.type != "note_on" or message.velocity <= 0:
            continue
        family = MIDI_FAMILY.get(int(message.note))
        if family is None:
            ignored[int(message.note)] = ignored.get(int(message.note), 0) + 1
            continue
        events[family].append(round(elapsed, 6))
    return events, ignored


def run_worker(command_template: str, audio_path: Path, *, timeout: float) -> dict[str, Any]:
    parts = split_command_line(command_template)
    if not parts or all("{audio}" not in part for part in parts):
        raise ValueError("worker command must contain {audio}")
    command = [part.replace("{audio}", str(audio_path)) for part in parts]
    completed = subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=timeout,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload.get("events"), dict):
        raise ValueError("worker output must contain an events object")
    return payload


def evaluate_dataset(
    root: Path,
    command_template: str,
    *,
    tolerance_seconds: float = 0.05,
    timeout_seconds: float = 300.0,
    limit: int | None = None,
    partition: str = "all",
) -> dict[str, Any]:
    rows = list(csv.DictReader((root / "metadata.csv").open(encoding="utf-8")))
    if partition not in {"all", "calibration", "heldout"}:
        raise ValueError(f"unsupported partition: {partition}")
    if partition != "all":
        wanted = 0 if partition == "calibration" else 1
        rows = [
            row for row in rows
            if hashlib.sha256(row["track_id"].encode("utf-8")).digest()[0] % 2 == wanted
        ]
    if limit is not None:
        rows = rows[: max(0, limit)]
    all_reference: dict[str, list[float]] = {}
    all_prediction: dict[str, list[float]] = {}
    offset = 0.0
    tracks = []
    ignored_total: dict[int, int] = {}
    worker_metadata: dict[str, Any] = {}
    for row in rows:
        audio_path = root / row["audio_path"]
        midi_path = root / row["midi_path"]
        reference, ignored = read_reference_midi(midi_path)
        payload = run_worker(command_template, audio_path, timeout=timeout_seconds)
        prediction = payload["events"]
        metrics = onset_event_metrics(
            reference, prediction, tolerance_seconds=tolerance_seconds,
        )
        high_percussion_metrics = onset_event_metrics(
            merged_event_family(reference, ("hihat", "cymbal")),
            merged_event_family(prediction, ("hihat", "cymbal")),
            tolerance_seconds=tolerance_seconds,
        )
        tracks.append({
            "track_id": row["track_id"],
            "style": row.get("style"),
            "duration_sec": float(row.get("duration_sec") or 0.0),
            "metrics": metrics,
            "high_percussion_metrics": high_percussion_metrics,
            "ignored_reference_pitches": ignored,
        })
        for pitch, count in ignored.items():
            ignored_total[pitch] = ignored_total.get(pitch, 0) + count
        for family, values in reference.items():
            all_reference.setdefault(family, []).extend(offset + float(value) for value in values)
        for family, values in prediction.items():
            all_prediction.setdefault(family, []).extend(
                offset + float(value.get("time", value)) for value in values
            )
        offset += float(row.get("duration_sec") or 0.0) + 1.0
        worker_metadata = {
            key: payload.get(key)
            for key in ("engine", "model_name", "model_version", "license", "class_mapping")
        }
    overall = onset_event_metrics(
        all_reference, all_prediction, tolerance_seconds=tolerance_seconds,
    )
    high_percussion_overall = onset_event_metrics(
        merged_event_family(all_reference, ("hihat", "cymbal")),
        merged_event_family(all_prediction, ("hihat", "cymbal")),
        tolerance_seconds=tolerance_seconds,
    )
    return {
        "benchmark": "MDB Drums++",
        "dataset_root": str(root),
        "dataset_license": "CC BY-NC-SA 4.0",
        "track_count": len(tracks),
        "partition": partition,
        "partition_rule": "sha256(track_id).first_byte_mod_2",
        "worker": worker_metadata,
        "overall": overall,
        "high_percussion_overall": high_percussion_overall,
        "high_percussion_release_gate": event_release_gate(high_percussion_overall),
        "release_gate": event_release_gate(overall),
        "per_class_release_gates": {
            family: event_release_gate(
                metrics,
                minimum_reference_events=50,
            )
            for family, metrics in overall["per_class"].items()
        },
        "ignored_reference_pitches": {
            str(key): value for key, value in sorted(ignored_total.items())
        },
        "tracks": tracks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--tolerance-ms", type=float, default=50.0)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--partition", choices=("all", "calibration", "heldout"), default="all")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_dataset(
        args.dataset_root,
        args.command,
        tolerance_seconds=args.tolerance_ms / 1000.0,
        timeout_seconds=args.timeout_seconds,
        limit=args.limit,
        partition=args.partition,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
