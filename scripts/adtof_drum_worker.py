#!/usr/bin/env python3
"""Optional ADTOF-PyTorch worker for Harbeat's JSON model contract.

The worker intentionally lives outside the application environment.  Install
ADTOF-PyTorch in a dedicated evaluation environment and configure:

    FEATURE_DRUM_TRANSCRIBER_COMMAND="python scripts/adtof_drum_worker.py --audio {audio}"

No model weights are copied into Harbeat.  Review the installed upstream
package and model licences before any distribution or commercial deployment.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from importlib import metadata
import json
from pathlib import Path
import tempfile
import sys
from typing import Any, Iterable, Sequence

import numpy as np


# ADTOF's five published output channels use these General MIDI pitches.
GM_DRUM_FAMILIES = {
    35: "kick",
    38: "snare",
    47: "tom",
    42: "hihat",
    49: "cymbal",
}


def _package_version() -> str:
    try:
        return metadata.version("adtof-pytorch")
    except metadata.PackageNotFoundError:
        return "unknown"


def peaks_to_events(
    peaks: dict[int, Iterable[float]],
    activations: np.ndarray,
    labels: Sequence[int],
    *,
    fps: int,
) -> dict[str, list[dict[str, Any]]]:
    """Convert peak-picked MIDI classes to the shared event contract.

    Confidence is the model activation at the nearest 100 Hz frame, not a
    fabricated fixed confidence.  The five-class model has only one hi-hat
    channel, so its subtype is deliberately ``closed_hihat_or_hat_family``.
    """
    values = np.asarray(activations, dtype=float)
    if values.ndim == 3:
        values = values[0]
    if values.ndim != 2 or values.shape[1] != len(labels):
        raise ValueError(
            f"activation shape {values.shape} does not match {len(labels)} labels"
        )
    events = {family: [] for family in GM_DRUM_FAMILIES.values()}
    for channel, midi_pitch in enumerate(labels):
        family = GM_DRUM_FAMILIES.get(int(midi_pitch))
        if family is None:
            continue
        for raw_time in peaks.get(int(midi_pitch), []):
            timestamp = float(raw_time)
            frame = int(np.clip(round(timestamp * fps), 0, values.shape[0] - 1))
            subtype = (
                "closed_hihat_or_hat_family" if int(midi_pitch) == 42
                else f"gm_{int(midi_pitch)}"
            )
            events[family].append({
                "time": round(timestamp, 4),
                "confidence": round(float(np.clip(values[frame, channel], 0.0, 1.0)), 4),
                "midi_pitch": int(midi_pitch),
                "subtype": subtype,
            })
    for family in events:
        events[family].sort(key=lambda item: item["time"])
    return events


def transcribe(
    audio_path: Path,
    *,
    device: str = "cpu",
    fps: int = 100,
    thresholds: Sequence[float] | None = None,
) -> dict[str, Any]:
    try:
        from adtof_pytorch import (
            FRAME_RNN_THRESHOLDS,
            LABELS_5,
            PeakPicker,
            transcribe_to_midi,
        )
    except ImportError as exc:
        raise RuntimeError(
            "adtof-pytorch is not installed; install it only in the optional model environment"
        ) from exc

    unused_midi = Path(tempfile.gettempdir()) / "harbeat-adtof-unused.mid"
    # Upstream currently prints weight-loading diagnostics to stdout.  The
    # parent adapter requires stdout to contain exactly one JSON object.
    with redirect_stdout(sys.stderr):
        activations = transcribe_to_midi(
            audio_path,
            unused_midi,
            fps=fps,
            return_activations=True,
            device=device,
        )
    resolved_thresholds = list(thresholds or FRAME_RNN_THRESHOLDS)
    if len(resolved_thresholds) != len(LABELS_5):
        raise ValueError(f"expected {len(LABELS_5)} thresholds, got {len(resolved_thresholds)}")
    picker = PeakPicker(thresholds=resolved_thresholds, fps=fps)
    peaks = picker.pick(activations, labels=LABELS_5, label_offset=0)[0]
    events = peaks_to_events(peaks, activations, LABELS_5, fps=fps)
    return {
        "engine": "adtof_pytorch_frame_rnn",
        "model_name": "ADTOF Frame_RNN five-class drum transcription",
        "model_version": _package_version(),
        "license": "upstream_license_review_required",
        "fps": fps,
        "class_mapping": {str(key): value for key, value in GM_DRUM_FAMILIES.items()},
        "thresholds": {
            str(label): float(threshold)
            for label, threshold in zip(LABELS_5, resolved_thresholds, strict=True)
        },
        "events": events,
        "event_count": sum(len(values) for values in events.values()),
        "limitations": [
            "five_class_model_does_not_separate_open_and_closed_hihat",
            "weights_are_not_distributed_by_harbeat",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--fps", type=int, default=100)
    parser.add_argument(
        "--thresholds",
        help="five comma-separated thresholds in ADTOF order: kick,snare,tom,hihat,cymbal",
    )
    args = parser.parse_args()
    thresholds = (
        [float(value.strip()) for value in args.thresholds.split(",")]
        if args.thresholds else None
    )
    print(json.dumps(
        transcribe(args.audio, device=args.device, fps=args.fps, thresholds=thresholds),
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
