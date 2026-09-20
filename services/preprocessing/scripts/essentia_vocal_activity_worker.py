#!/usr/bin/env python3
"""JSON worker for time-local voice activity and calibrated vocal density.

The worker uses Essentia's official YAMNet embedding plus the official
voice/instrumental classification head.  Model weights are supplied at runtime
and are deliberately not bundled with Harbeat.

The decision threshold and Platt calibration constants were selected only on
the 16-track validation split of the public Jamendo Singing Voice Detection
Corpus.  The official test split and the 61-track train split remain external
held-out checks in ``evaluate_jamendo_vocal_activity.py``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np


SAMPLE_RATE = 16_000
PATCH_WINDOW_SECONDS = 0.96
PATCH_HOP_SECONDS = 0.93
VOICE_THRESHOLD = 0.88
PLATT_COEFFICIENT = 6.001489921408274
PLATT_INTERCEPT = -4.5789610411637565
CALIBRATION_VERSION = "jamendo_svd_valid16_platt_v1"


def calibrate_probabilities(values: Iterable[float]) -> np.ndarray:
    """Convert raw head scores into validation-calibrated probabilities."""
    raw = np.asarray(list(values), dtype=float)
    logits = PLATT_COEFFICIENT * raw + PLATT_INTERCEPT
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -40.0, 40.0)))


def merge_activity_ranges(
    probabilities: Iterable[float],
    *,
    duration_seconds: float,
    threshold: float = VOICE_THRESHOLD,
) -> list[dict[str, float]]:
    """Merge overlapping active model patches into auditable time ranges."""
    raw = np.asarray(list(probabilities), dtype=float)
    active_indices = np.flatnonzero(raw >= float(threshold))
    if not len(active_indices):
        return []
    ranges: list[dict[str, float]] = []
    start_index = previous = int(active_indices[0])
    for value in active_indices[1:]:
        index = int(value)
        if index > previous + 1:
            ranges.append({
                "start": round(start_index * PATCH_HOP_SECONDS, 4),
                "end": round(min(
                    duration_seconds,
                    previous * PATCH_HOP_SECONDS + PATCH_WINDOW_SECONDS,
                ), 4),
            })
            start_index = index
        previous = index
    ranges.append({
        "start": round(start_index * PATCH_HOP_SECONDS, 4),
        "end": round(min(
            duration_seconds,
            previous * PATCH_HOP_SECONDS + PATCH_WINDOW_SECONDS,
        ), 4),
    })
    return ranges


def build_result(
    raw_probabilities: Iterable[float],
    *,
    duration_seconds: float,
    include_frames: bool = True,
) -> dict[str, Any]:
    raw = np.clip(np.asarray(list(raw_probabilities), dtype=float), 0.0, 1.0)
    calibrated = calibrate_probabilities(raw)
    active = raw >= VOICE_THRESHOLD
    frames = []
    if include_frames:
        for index, (raw_value, calibrated_value, is_active) in enumerate(
            zip(raw, calibrated, active, strict=True)
        ):
            start = index * PATCH_HOP_SECONDS
            frames.append({
                "start": round(start, 4),
                "end": round(min(duration_seconds, start + PATCH_WINDOW_SECONDS), 4),
                "center": round(start + PATCH_WINDOW_SECONDS / 2.0, 4),
                "voice_probability_raw": round(float(raw_value), 6),
                "voice_probability_calibrated": round(float(calibrated_value), 6),
                "active": bool(is_active),
            })
    return {
        "engine": "essentia_yamnet_voice_instrumental",
        "model_name": "YAMNet embedding + voice/instrumental head",
        "model_version": "audioset-yamnet-1 + voice_instrumental-audioset-yamnet-1",
        "license": "Essentia-model-weights-CC-BY-NC-SA-4.0-review-required",
        "sample_rate": SAMPLE_RATE,
        "duration_seconds": round(float(duration_seconds), 4),
        "frame_count": int(len(raw)),
        "patch_window_seconds": PATCH_WINDOW_SECONDS,
        "patch_hop_seconds": PATCH_HOP_SECONDS,
        "voice_decision_threshold": VOICE_THRESHOLD,
        "vocal_activity_fraction": round(float(np.mean(active)) if len(active) else 0.0, 6),
        # Mean calibrated posterior estimates the fraction of the song that
        # contains singing or spoken voice.  It is not rescaled to make an
        # ordinary vocal song look artificially "maximally dense".
        "vocal_density": round(float(np.mean(calibrated)) if len(calibrated) else 0.0, 6),
        "mean_voice_probability_raw": round(float(np.mean(raw)) if len(raw) else 0.0, 6),
        "calibration": {
            "method": "platt_logistic_on_jamendo_validation_frames",
            "version": CALIBRATION_VERSION,
            "coefficient": PLATT_COEFFICIENT,
            "intercept": PLATT_INTERCEPT,
        },
        "time_ranges": merge_activity_ranges(
            raw, duration_seconds=duration_seconds, threshold=VOICE_THRESHOLD,
        ),
        "frames": frames,
        "limitations": [
            "voice_label_combines_singing_and_spoken_voice",
            "does_not_classify_rap_singing_or_vocal_chops",
            "external_model_weights_are_not_distributed_by_harbeat",
        ],
    }


def analyze(
    audio_path: Path,
    *,
    embedding_model_path: Path,
    classifier_model_path: Path,
    include_frames: bool = True,
) -> dict[str, Any]:
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)
    for path in (embedding_model_path, classifier_model_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    import essentia
    import essentia.standard as essentia_standard

    essentia.log.infoActive = False
    essentia.log.warningActive = False
    audio = np.asarray(essentia_standard.MonoLoader(
        filename=str(audio_path), sampleRate=SAMPLE_RATE, resampleQuality=4,
    )(), dtype=np.float32)
    embedding_model = essentia_standard.TensorflowPredictVGGish(
        graphFilename=str(embedding_model_path),
        input="melspectrogram",
        output="embeddings",
    )
    classifier = essentia_standard.TensorflowPredict2D(
        graphFilename=str(classifier_model_path), output="model/Softmax",
    )
    embeddings = embedding_model(audio)
    predictions = np.asarray(classifier(embeddings), dtype=float)
    if predictions.ndim != 2 or predictions.shape[1] != 2:
        raise ValueError(f"unexpected voice head output shape: {predictions.shape}")
    duration_seconds = len(audio) / SAMPLE_RATE
    return build_result(
        predictions[:, 1],
        duration_seconds=duration_seconds,
        include_frames=include_frames,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--embedding-model", type=Path, required=True)
    parser.add_argument("--classifier-model", type=Path, required=True)
    parser.add_argument("--no-frames", action="store_true")
    args = parser.parse_args()
    print(json.dumps(analyze(
        args.audio,
        embedding_model_path=args.embedding_model,
        classifier_model_path=args.classifier_model,
        include_frames=not args.no_frames,
    ), ensure_ascii=False))


if __name__ == "__main__":
    main()
