#!/usr/bin/env python3
"""Evaluate the optional Basic Pitch route on isolated BabySlakh bass stems.

BabySlakh supplies rendered stems and the exact MIDI used to render them.  The
calibration split may select a confidence threshold; the hash-disjoint heldout
split alone decides whether the route can be promoted to validated evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Iterable

import mido
import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
WORKER = ROOT / "scripts" / "basic_pitch_bass_worker.py"

from app.modules.library.bass_feature_analysis import (  # noqa: E402
    _bass_groove_descriptors,
    _collapse_simultaneous_bass_notes,
)
from app.modules.library.benchmark_evaluation import binary_metrics  # noqa: E402


def _split_id(value: str) -> str:
    return "calibration" if hashlib.sha256(value.encode()).digest()[0] % 2 == 0 else "heldout"


def read_midi_notes(path: Path) -> list[dict]:
    """Read absolute note seconds with a complete MIDI tempo map."""
    midi = mido.MidiFile(path)
    tempo = 500_000
    now = 0.0
    active: dict[tuple[int, int], list[tuple[float, int]]] = {}
    notes: list[dict] = []
    for message in mido.merge_tracks(midi.tracks):
        now += mido.tick2second(message.time, midi.ticks_per_beat, tempo)
        if message.type == "set_tempo":
            tempo = int(message.tempo)
            continue
        if message.type == "note_on" and message.velocity > 0:
            active.setdefault((message.channel, message.note), []).append((now, message.velocity))
        elif message.type in {"note_off", "note_on"}:
            stack = active.get((message.channel, message.note)) or []
            if not stack:
                continue
            start, velocity = stack.pop(0)
            if now > start:
                notes.append({
                    "start": float(start),
                    "end": float(now),
                    "midi": float(message.note),
                    "velocity": int(velocity),
                })
    return sorted(notes, key=lambda item: (item["start"], item["midi"], item["end"]))


def read_midi_grid(path: Path) -> tuple[list[float], list[float]]:
    """Return exact beat and bar-start seconds from MIDI tempo/meter maps."""
    midi = mido.MidiFile(path)
    absolute_tick = 0
    tempo_events = [(0, 500_000)]
    signature_events = [(0, 4, 4)]
    for message in mido.merge_tracks(midi.tracks):
        absolute_tick += int(message.time)
        if message.type == "set_tempo":
            tempo_events.append((absolute_tick, int(message.tempo)))
        elif message.type == "time_signature":
            signature_events.append((absolute_tick, int(message.numerator), int(message.denominator)))
    total_ticks = absolute_tick

    tempo_events = sorted(dict((tick, tempo) for tick, tempo in tempo_events).items())

    def to_seconds(target_tick: float) -> float:
        seconds = 0.0
        previous_tick = 0.0
        tempo = 500_000
        for event_tick, event_tempo in tempo_events:
            if event_tick > target_tick:
                break
            seconds += mido.tick2second(event_tick - previous_tick, midi.ticks_per_beat, tempo)
            previous_tick = float(event_tick)
            tempo = int(event_tempo)
        seconds += mido.tick2second(target_tick - previous_tick, midi.ticks_per_beat, tempo)
        return float(seconds)

    beat_ticks = np.arange(0, total_ticks + midi.ticks_per_beat, midi.ticks_per_beat, dtype=float)
    beat_times = [to_seconds(value) for value in beat_ticks]

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
        value = float(start_tick)
        while value < end_tick and value <= total_ticks:
            downbeat_ticks.append(value)
            value += bar_ticks
    downbeat_times = [to_seconds(value) for value in sorted(set(downbeat_ticks))]
    return beat_times, downbeat_times


def note_metrics(
    reference: Iterable[dict],
    predicted: Iterable[dict],
    *,
    onset_tolerance: float = 0.05,
    pitch_tolerance: float = 0.5,
) -> dict:
    """Class-aware one-to-one note matching at 50 ms and 50 cents."""
    refs = list(reference)
    preds = list(predicted)
    candidates = []
    for p_index, pred in enumerate(preds):
        for r_index, ref in enumerate(refs):
            onset_error = abs(float(pred["start"]) - float(ref["start"]))
            pitch_error = abs(float(pred["midi"]) - float(ref["midi"]))
            if onset_error <= onset_tolerance and pitch_error <= pitch_tolerance:
                candidates.append((onset_error, pitch_error, p_index, r_index))
    used_predictions: set[int] = set()
    used_references: set[int] = set()
    onset_errors: list[float] = []
    pitch_errors: list[float] = []
    for onset_error, pitch_error, p_index, r_index in sorted(candidates):
        if p_index in used_predictions or r_index in used_references:
            continue
        used_predictions.add(p_index)
        used_references.add(r_index)
        onset_errors.append(onset_error)
        pitch_errors.append(pitch_error)
    true_positive = len(used_predictions)
    false_positive = len(preds) - true_positive
    false_negative = len(refs) - true_positive
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    return {
        "reference_count": len(refs),
        "predicted_count": len(preds),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "mean_onset_error_ms": round(sum(onset_errors) / max(1, len(onset_errors)) * 1000, 3),
        "mean_pitch_error_cents": round(sum(pitch_errors) / max(1, len(pitch_errors)) * 100, 3),
    }


def _merge_metrics(reference: list[dict], predicted: list[dict], confidence: float) -> dict:
    collapsed = _collapse_simultaneous_bass_notes(predicted)
    accepted = [item for item in collapsed if float(item.get("confidence", 0.0)) >= confidence]
    return note_metrics(reference, accepted)


def _combine_track_metrics(values: list[dict]) -> dict:
    """Micro-average counts without ever matching notes across different songs."""
    reference_count = sum(item["reference_count"] for item in values)
    predicted_count = sum(item["predicted_count"] for item in values)
    true_positive = sum(item["true_positive"] for item in values)
    false_positive = sum(item["false_positive"] for item in values)
    false_negative = sum(item["false_negative"] for item in values)
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    macro_precision = sum(item["precision"] for item in values) / max(1, len(values))
    macro_recall = sum(item["recall"] for item in values) / max(1, len(values))
    macro_f1 = sum(item["f1"] for item in values) / max(1, len(values))
    return {
        "reference_count": reference_count,
        "predicted_count": predicted_count,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "macro_f1": round(macro_f1, 4),
    }


def _groove_events(notes: list[dict], *, confidence_threshold: float) -> list[dict]:
    events = []
    candidates = (
        _collapse_simultaneous_bass_notes(notes)
        if any("confidence" in item for item in notes) else notes
    )
    for note in candidates:
        confidence = float(note.get("confidence", 1.0))
        if confidence < confidence_threshold:
            continue
        midi = float(note["midi"])
        events.append({
            "time": float(note["start"]),
            "fundamental_hz": 440.0 * 2.0 ** ((midi - 69.0) / 12.0),
            "voiced_strength": confidence,
            "note_duration_sec": float(note["end"]) - float(note["start"]),
            "decay_sec": float(note["end"]) - float(note["start"]),
            "note_event_method": "basic_pitch_note_event",
        })
    return events


def descriptor_metrics(rows: list[dict], threshold: float) -> dict:
    """Compare song-level groove descriptors with source-MIDI truth."""
    fields = {
        "bass_syncopation": "syncopation_score",
        "bass_staccato_ratio": "staccato_score",
        "bass_octave_pattern": "octave_score",
        "bass_riff_repetition": "riff_score",
    }
    values = {name: [] for name in fields}
    for row in rows:
        reference = _bass_groove_descriptors(
            _groove_events(row["reference"], confidence_threshold=0.0),
            np.asarray(row["beat_points"]),
            np.asarray(row["downbeats"]),
            np.asarray([]),
        )
        predicted = _bass_groove_descriptors(
            _groove_events(row["predicted"], confidence_threshold=threshold),
            np.asarray(row["beat_points"]),
            np.asarray(row["downbeats"]),
            np.asarray([]),
        )
        for name, field in fields.items():
            values[name].append((float(reference[field]), float(predicted[field])))

    result = {}
    for name, pairs in values.items():
        reference = np.asarray([pair[0] for pair in pairs], dtype=float)
        predicted = np.asarray([pair[1] for pair in pairs], dtype=float)
        errors = np.abs(reference - predicted)
        reference_labels = reference >= 0.55
        predicted_labels = predicted >= 0.55
        class_count = len(set(reference_labels.tolist()))
        result[name] = {
            "sample_count": len(pairs),
            "mean_absolute_error": round(float(np.mean(errors)), 4) if len(errors) else None,
            "within_0_20_fraction": round(float(np.mean(errors <= 0.20)), 4) if len(errors) else None,
            "binary_accuracy_at_0_55": round(float(np.mean(reference_labels == predicted_labels)), 4) if len(errors) else None,
            "reference_positive_count": int(np.sum(reference_labels)),
            "reference_negative_count": int(np.sum(~reference_labels)),
            "reference_class_count": class_count,
            "validated": bool(
                len(pairs) >= 8
                and float(np.mean(errors <= 0.20)) >= 0.80
                and float(np.mean(reference_labels == predicted_labels)) >= 0.80
                and class_count == 2
                and int(np.sum(reference_labels)) >= 2
                and int(np.sum(~reference_labels)) >= 2
            ),
        }
    return result


def _descriptor_release_gate(
    metrics: dict,
    *,
    track_count: int,
) -> dict:
    reasons = []
    if track_count < 5:
        reasons.append("fewer_than_5_heldout_tracks")
    if int(metrics.get("sample_count", 0)) < 50:
        reasons.append("fewer_than_50_heldout_windows")
    if int(metrics.get("positive_count", 0)) < 10:
        reasons.append("fewer_than_10_positive_windows")
    if int(metrics.get("negative_count", 0)) < 10:
        reasons.append("fewer_than_10_negative_windows")
    if float(metrics.get("within_0_20_fraction", 0.0)) < 0.80:
        reasons.append("continuous_error_coverage_below_0_80")
    for name in ("accuracy", "precision", "recall", "f1"):
        if float(metrics.get(name, 0.0)) < 0.80:
            reasons.append(f"{name}_below_0_80")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "thresholds": {
            "minimum_heldout_tracks": 5,
            "minimum_heldout_windows": 50,
            "minimum_windows_per_class": 10,
            "minimum_within_0_20_fraction": 0.80,
            "minimum_accuracy_precision_recall_f1": 0.80,
        },
    }


def descriptor_window_metrics(
    rows: list[dict],
    threshold: float,
    *,
    bars_per_window: int = 4,
) -> dict:
    """Audit descriptor propagation on track-disjoint four-bar windows.

    Source MIDI defines the reference feature. Basic Pitch notes define the
    production-side estimate. Windows increase musical-condition coverage but
    the gate still requires several independent held-out songs.
    """
    fields = {
        "bass_syncopation": "syncopation_score",
        "bass_staccato_ratio": "staccato_score",
        "bass_octave_pattern": "octave_score",
        "bass_riff_repetition": "riff_score",
    }
    values = {name: [] for name in fields}
    contributing_tracks: set[str] = set()
    for row in rows:
        beat_points = np.asarray(row["beat_points"], dtype=float)
        downbeats = np.asarray(row["downbeats"], dtype=float)
        reference_events = _groove_events(row["reference"], confidence_threshold=0.0)
        predicted_events = _groove_events(row["predicted"], confidence_threshold=threshold)
        for index in range(0, len(downbeats) - bars_per_window, bars_per_window):
            start = float(downbeats[index])
            end = float(downbeats[index + bars_per_window])
            reference = [
                event for event in reference_events if start <= float(event["time"]) < end
            ]
            # Sparse rests do not contain enough ordered evidence to define a
            # bass-groove window, so they are unknown rather than negatives.
            if len(reference) < 4:
                continue
            predicted = [
                event for event in predicted_events if start <= float(event["time"]) < end
            ]
            local_beats = beat_points[
                (beat_points >= start - 1e-6) & (beat_points <= end + 1e-6)
            ]
            local_downbeats = downbeats[index:index + bars_per_window + 1]
            reference_values = _bass_groove_descriptors(
                reference, local_beats, local_downbeats, np.asarray([]),
            )
            predicted_values = _bass_groove_descriptors(
                predicted, local_beats, local_downbeats, np.asarray([]),
            )
            contributing_tracks.add(str(row["id"]))
            for name, field in fields.items():
                values[name].append((
                    float(reference_values[field]),
                    float(predicted_values[field]),
                ))

    result = {}
    for name, pairs in values.items():
        reference = np.asarray([pair[0] for pair in pairs], dtype=float)
        predicted = np.asarray([pair[1] for pair in pairs], dtype=float)
        errors = np.abs(reference - predicted)
        binary = binary_metrics(
            (bool(value) for value in reference >= 0.55),
            (bool(value) for value in predicted >= 0.55),
        )
        metrics = {
            **binary,
            "mean_absolute_error": round(float(np.mean(errors)), 4) if len(errors) else None,
            "within_0_20_fraction": round(float(np.mean(errors <= 0.20)), 4) if len(errors) else None,
        }
        result[name] = {
            **metrics,
            "release_gate": _descriptor_release_gate(
                metrics, track_count=len(contributing_tracks),
            ),
        }
    return {
        "window_bars": bars_per_window,
        "heldout_track_count": len(contributing_tracks),
        "features": result,
    }


def _bass_stems(dataset_root: Path) -> list[dict]:
    rows = []
    for track_dir in sorted(dataset_root.glob("Track*")):
        metadata_path = track_dir / "metadata.yaml"
        if not metadata_path.is_file():
            continue
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
        for stem_id, stem in sorted((metadata.get("stems") or {}).items()):
            if stem.get("inst_class") != "Bass":
                continue
            audio_path = track_dir / "stems" / f"{stem_id}.wav"
            midi_path = track_dir / "MIDI" / f"{stem_id}.mid"
            if audio_path.is_file() and midi_path.is_file():
                identity = f"{track_dir.name}/{stem_id}"
                rows.append({
                    "id": identity,
                    "split": _split_id(identity),
                    "audio_path": audio_path,
                    "midi_path": midi_path,
                    "instrument": stem.get("midi_program_name"),
                    "program_num": stem.get("program_num"),
                    "plugin_name": stem.get("plugin_name"),
                })
    return rows


def _predict(worker_python: Path, audio_path: Path, cache_path: Path) -> dict:
    if cache_path.is_file():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    completed = subprocess.run(
        [str(worker_python), str(WORKER), "--audio", str(audio_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def evaluate(dataset_root: Path, worker_python: Path, cache_dir: Path) -> dict:
    stems = _bass_stems(dataset_root)
    rows = []
    for index, stem in enumerate(stems, start=1):
        print(f"[{index}/{len(stems)}] {stem['id']}", file=sys.stderr, flush=True)
        reference = read_midi_notes(stem["midi_path"])
        beat_points, downbeats = read_midi_grid(stem["midi_path"])
        # Slakh bass annotations are one octave above their rendered sounding
        # pitch.  YourMT3's Slakh preprocessing applies this same -12 semitone
        # correction for GM bass programs 32..39, except the one Jay Bass slap
        # patch whose MIDI is already at sounding pitch.
        bass_octave_shift = (
            -12.0
            if stem.get("program_num") in range(32, 40)
            and stem.get("plugin_name") != "scarbee_jay_bass_slap_both.nkm"
            else 0.0
        )
        if bass_octave_shift:
            for note in reference:
                note["midi"] += bass_octave_shift
        prediction = _predict(
            worker_python,
            stem["audio_path"],
            cache_dir / f"{stem['id'].replace('/', '__')}.json",
        )
        rows.append({
            "id": stem["id"],
            "split": stem["split"],
            "instrument": stem["instrument"],
            "reference": reference,
            "predicted": prediction.get("note_events") or [],
            "engine": prediction.get("engine"),
            "model_version": prediction.get("model_version"),
            "reference_pitch_shift_semitones": bass_octave_shift,
            "beat_points": beat_points,
            "downbeats": downbeats,
        })

    thresholds = [round(value / 100, 2) for value in range(20, 81, 5)]
    calibration_rows = [row for row in rows if row["split"] == "calibration"]
    heldout_rows = [row for row in rows if row["split"] == "heldout"]

    def combined(selected: list[dict], threshold: float) -> dict:
        return _combine_track_metrics([
            _merge_metrics(row["reference"], row["predicted"], threshold)
            for row in selected
        ])

    calibration_curve = [
        {"confidence_threshold": threshold, **combined(calibration_rows, threshold)}
        for threshold in thresholds
    ]
    # Threshold selection uses development data only.  The release contract
    # requires both precision and recall across songs, so optimize the weaker
    # macro-average before micro F1.  This prevents one note-dense song from
    # hiding failures on quieter or differently articulated bass patches.
    selected = max(
        calibration_curve,
        key=lambda item: (
            min(item["macro_precision"], item["macro_recall"]),
            item["macro_f1"],
            item["f1"],
            item["precision"],
        ),
    )
    threshold = float(selected["confidence_threshold"])
    heldout = combined(heldout_rows, threshold)
    heldout_descriptors = descriptor_metrics(heldout_rows, threshold)
    heldout_descriptor_windows = descriptor_window_metrics(heldout_rows, threshold)
    release_gate = {
        "minimum_reference_notes": 500,
        "minimum_precision": 0.80,
        "minimum_recall": 0.80,
        "minimum_f1": 0.80,
        "passed": (
            heldout["reference_count"] >= 500
            and heldout["precision"] >= 0.80
            and heldout["recall"] >= 0.80
            and heldout["f1"] >= 0.80
            and heldout["macro_precision"] >= 0.80
            and heldout["macro_recall"] >= 0.80
            and heldout["macro_f1"] >= 0.80
        ),
    }
    return {
        "benchmark": "BabySlakh 16k isolated Bass stems and source MIDI",
        "stem_count": len(rows),
        "calibration_stem_count": len(calibration_rows),
        "heldout_stem_count": len(heldout_rows),
        "matching": {"onset_tolerance_ms": 50, "pitch_tolerance_cents": 50},
        "calibration_curve": calibration_curve,
        "selected_confidence_threshold": threshold,
        "heldout_metrics": heldout,
        "heldout_descriptor_metrics": heldout_descriptors,
        "heldout_descriptor_window_metrics": heldout_descriptor_windows,
        "release_gate": release_gate,
        "rows": [
            {
                "id": row["id"],
                "split": row["split"],
                "instrument": row["instrument"],
                "reference_pitch_shift_semitones": row["reference_pitch_shift_semitones"],
                "metrics": _merge_metrics(row["reference"], row["predicted"], threshold),
            }
            for row in rows
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--worker-python", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.dataset_root, args.worker_python, args.cache_dir)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
