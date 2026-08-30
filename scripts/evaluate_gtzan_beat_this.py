#!/usr/bin/env python3
"""Evaluate Beat This final0 on its official, unseen GTZAN test set.

The official Beat This release documents that ``final0`` is trained on every
supported dataset except GTZAN.  This evaluator therefore consumes the
official GTZAN spectrogram archive and annotations directly, without decoding
or preprocessing audio differently from the model's published evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from collections.abc import Mapping
from zipfile import ZipFile

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.analysis import (  # noqa: E402
    _bpm_from_beat_times,
    _detect_time_signature,
    _downbeat_match_metrics,
)


EXPECTED_ARCHIVE_MD5 = "39a7dfe6a6b0a5279a94d770506db879"


class MemoryviewIO:
    """Minimal read-only file adapter used by the official Beat This loader."""

    def __init__(self, buffer):
        self._buffer = memoryview(buffer).cast("B")
        self._position = 0

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._position = offset
        elif whence == 1:
            self._position += offset
        elif whence == 2:
            self._position = self._buffer.nbytes + offset
        return self._position

    def read(self, size: int = -1) -> bytes:
        data = self._buffer[
            self._position:self._position + size if size >= 0 else None
        ].tobytes()
        self._position += len(data)
        return data

    def tell(self) -> int:
        return self._position

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False


class MemmappedNpzFile(Mapping):
    """Lazy zero-copy reader for the official uncompressed GTZAN NPZ."""

    def __init__(self, path: Path):
        with ZipFile(path, mode="r") as archive:
            self._offsets = {
                entry.filename[:-4]: (entry.header_offset, entry.file_size)
                for entry in archive.infolist()
                if entry.filename.endswith(".npy") and entry.compress_type == 0
            }
        self.files = list(self._offsets)
        self._mmap = np.memmap(path, mode="r")

    def __iter__(self):
        return iter(self.files)

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, name: str) -> np.ndarray:
        header_offset, file_size = self._offsets[name]
        file_name_length, extra_length = struct.unpack(
            "<2H", self._mmap[header_offset + 26:header_offset + 30],
        )
        npy_start = header_offset + 30 + file_name_length + extra_length
        npy_end = npy_start + file_size
        stream = MemoryviewIO(self._mmap)
        stream.seek(npy_start)
        version = np.lib.format.read_magic(stream)
        np.lib.format._check_version(version)
        shape, fortran, dtype = np.lib.format._read_array_header(stream, version)
        return (
            self._mmap[stream.tell():npy_end]
            .view(dtype=dtype)
            .reshape(shape, order="F" if fortran else "C")
        )


def read_annotations(path: Path) -> tuple[list[float], list[float]]:
    beats: list[float] = []
    downbeats: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        columns = line.split()
        if len(columns) < 2:
            continue
        time = float(columns[0])
        position = int(float(columns[1]))
        beats.append(time)
        if position == 1:
            downbeats.append(time)
    return beats, downbeats


def reference_meter(path: Path) -> int | None:
    positions = [
        int(float(columns[1]))
        for line in path.read_text(encoding="utf-8").splitlines()
        if len(columns := line.split()) >= 2
    ]
    meter = max(positions, default=0)
    return meter if meter in {3, 4} else None


def trim_events(values: list[float] | np.ndarray, *, minimum_time: float = 5.0) -> list[float]:
    """Match Beat This's published protocol: ignore the first five seconds."""
    return [float(value) for value in values if float(value) >= minimum_time]


def event_metrics(predicted: list[float], reference: list[float], tolerance: float = 0.07) -> dict:
    result = _downbeat_match_metrics(predicted, reference, tolerance=tolerance)
    return {
        **result,
        "predicted_count": len(predicted),
        "reference_count": len(reference),
    }


def combine_track_metrics(values: list[dict]) -> dict:
    matches = sum(int(item["matches"]) for item in values)
    predicted = sum(int(item["predicted_count"]) for item in values)
    reference = sum(int(item["reference_count"]) for item in values)
    precision = matches / max(1, predicted)
    recall = matches / max(1, reference)
    f1 = 2.0 * precision * recall / max(1e-12, precision + recall)
    return {
        "track_count": len(values),
        "reference_count": reference,
        "predicted_count": predicted,
        "matches": matches,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "macro_precision": round(sum(item["precision"] for item in values) / max(1, len(values)), 4),
        "macro_recall": round(sum(item["recall"] for item in values) / max(1, len(values)), 4),
        "macro_f1": round(sum(item["f1"] for item in values) / max(1, len(values)), 4),
    }


def release_gate(metrics: dict, *, minimum_tracks: int = 30) -> dict:
    reasons = []
    if metrics["track_count"] < minimum_tracks:
        reasons.append("insufficient_tracks")
    for name in ("precision", "recall", "f1", "macro_precision", "macro_recall", "macro_f1"):
        if float(metrics[name]) < 0.80:
            reasons.append(f"{name}_below_0_80")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "minimum_tracks": minimum_tracks,
        "minimum_all_precision_recall_f1": 0.80,
    }


def meter_metrics(rows: list[dict]) -> dict:
    usable = [
        row for row in rows
        if row.get("reference_meter") in {3, 4} and row.get("predicted_meter") in {3, 4}
    ]
    per_class = {}
    for meter in (3, 4):
        selected = [row for row in usable if row["reference_meter"] == meter]
        per_class[str(meter)] = {
            "sample_count": len(selected),
            "recall": round(
                sum(row["predicted_meter"] == meter for row in selected) / max(1, len(selected)), 4,
            ),
        }
    accuracy = sum(
        row["predicted_meter"] == row["reference_meter"] for row in usable
    ) / max(1, len(usable))
    balanced_accuracy = sum(item["recall"] for item in per_class.values()) / 2.0
    return {
        "sample_count": len(usable),
        "accuracy": round(accuracy, 4),
        "balanced_accuracy": round(balanced_accuracy, 4),
        "per_class": per_class,
    }


def meter_release_gate(metrics: dict) -> dict:
    reasons = []
    if any(item["sample_count"] < 10 for item in metrics["per_class"].values()):
        reasons.append("fewer_than_10_tracks_in_a_meter_class")
    if metrics["accuracy"] < 0.80:
        reasons.append("accuracy_below_0_80")
    if metrics["balanced_accuracy"] < 0.80:
        reasons.append("balanced_accuracy_below_0_80")
    return {"passed": not reasons, "reasons": reasons}


def evaluate(
    spectrogram_archive: Path,
    annotation_root: Path,
    *,
    checkpoint: str = "final0",
    device: str = "cpu",
    limit: int | None = None,
    downbeat_confidence_threshold: float = 0.925,
    meter_balanced_per_class: int | None = None,
) -> dict:
    import torch
    from beat_this.inference import Spect2Frames
    from beat_this.model.postprocessor import Postprocessor

    spectrograms = MemmappedNpzFile(spectrogram_archive)
    annotation_files = [
        path for path in annotation_root.glob("*.beats")
        if f"{path.stem}/track" in spectrograms
    ]
    annotation_files.sort(key=lambda path: hashlib.sha256(path.stem.encode()).digest())
    if meter_balanced_per_class is not None:
        annotation_files = [
            path
            for meter in (3, 4)
            for path in [item for item in annotation_files if reference_meter(item) == meter][
                :max(0, meter_balanced_per_class)
            ]
        ]
        annotation_files.sort(key=lambda path: hashlib.sha256(path.stem.encode()).digest())
    if limit is not None:
        annotation_files = annotation_files[:max(0, limit)]

    model = Spect2Frames(checkpoint_path=checkpoint, device=device, float16=False)
    postprocessor = Postprocessor(type="minimal", fps=50)
    rows = []
    for index, annotation_path in enumerate(annotation_files, start=1):
        track_id = annotation_path.stem
        print(f"[{index}/{len(annotation_files)}] {track_id}", file=sys.stderr, flush=True)
        spectrogram = torch.as_tensor(
            np.asarray(spectrograms[f"{track_id}/track"], dtype=np.float32),
            device=device,
        )
        beat_logits, downbeat_logits = model(spectrogram)
        predicted_beats, predicted_downbeats = postprocessor(beat_logits, downbeat_logits)
        downbeat_frames = np.clip(
            np.rint(np.asarray(predicted_downbeats) * 50.0).astype(int),
            0,
            max(0, len(downbeat_logits) - 1),
        )
        downbeat_peak_probability_mean = (
            float(torch.sigmoid(downbeat_logits[downbeat_frames]).mean().item())
            if len(downbeat_frames) and len(downbeat_logits) else 0.0
        )
        reference_beats, reference_downbeats = read_annotations(annotation_path)
        beat_metrics = event_metrics(
            trim_events(predicted_beats), trim_events(reference_beats),
        )
        downbeat_metrics = event_metrics(
            trim_events(predicted_downbeats), trim_events(reference_downbeats),
        )
        reference_time_signature = reference_meter(annotation_path)
        predicted_time_signature = _detect_time_signature(
            predicted_beats,
            [float(value) for value in predicted_downbeats],
            bpm=_bpm_from_beat_times(predicted_beats),
        )
        rows.append({
            "track_id": track_id,
            "genre": track_id.split("_")[1],
            "split": (
                "calibration"
                if hashlib.sha256(track_id.encode()).digest()[0] % 2 == 0
                else "heldout"
            ),
            "beat_metrics": beat_metrics,
            "downbeat_metrics": downbeat_metrics,
            "downbeat_peak_probability_mean": round(downbeat_peak_probability_mean, 6),
            "downbeat_accepted": downbeat_peak_probability_mean >= downbeat_confidence_threshold,
            "reference_meter": reference_time_signature,
            "predicted_meter": int(predicted_time_signature["numerator"]),
        })

    partitions = {}
    for split in ("calibration", "heldout"):
        selected = [row for row in rows if row["split"] == split]
        partitions[split] = {
            "beats": combine_track_metrics([row["beat_metrics"] for row in selected]),
            "downbeats_raw": combine_track_metrics([row["downbeat_metrics"] for row in selected]),
            "downbeats_accepted": combine_track_metrics([
                row["downbeat_metrics"] for row in selected if row["downbeat_accepted"]
            ]),
            "downbeat_coverage": round(
                sum(row["downbeat_accepted"] for row in selected) / max(1, len(selected)), 4,
            ),
            "meter_accepted": meter_metrics([
                row for row in selected if row["downbeat_accepted"]
            ]),
        }
    heldout = partitions["heldout"]
    return {
        "benchmark": "Beat This official GTZAN unseen test set",
        "model": f"beat_this:{checkpoint}",
        "postprocessor": "minimal_50fps_probability_gt_0.5_peak_nms_70ms",
        "sample_count": len(rows),
        "evaluation_trim_seconds": 5.0,
        "matching_tolerance_ms": 70,
        "downbeat_confidence_gate": {
            "metric": "mean_sigmoid_probability_at_emitted_downbeat_peaks",
            "threshold": downbeat_confidence_threshold,
            "selected_using": "calibration partition only",
        },
        "archive_expected_md5": EXPECTED_ARCHIVE_MD5,
        "partitions": partitions,
        "release_gates": {
            "beats": release_gate(heldout["beats"]),
            "downbeats_raw": release_gate(heldout["downbeats_raw"]),
            "downbeats_accepted": release_gate(heldout["downbeats_accepted"]),
            "meter_accepted": meter_release_gate(heldout["meter_accepted"]),
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spectrogram-archive", type=Path, required=True)
    parser.add_argument("--annotation-root", type=Path, required=True)
    parser.add_argument("--checkpoint", default="final0")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--downbeat-confidence-threshold", type=float, default=0.925)
    parser.add_argument("--meter-balanced-per-class", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(
        args.spectrogram_archive,
        args.annotation_root,
        checkpoint=args.checkpoint,
        device=args.device,
        limit=args.limit,
        downbeat_confidence_threshold=args.downbeat_confidence_threshold,
        meter_balanced_per_class=args.meter_balanced_per_class,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
