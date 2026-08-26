#!/usr/bin/env python3
"""PANNs AudioSet tag worker using the shared HarBeat JSON contract."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys

import librosa
import numpy as np


RELEVANT_LABELS = {
    "Clapping",
    "Drum kit",
    "Drum machine",
    "Drum",
    "Snare drum",
    "Rimshot",
    "Drum roll",
    "Bass drum",
    "Cymbal",
    "Hi-hat",
    "Wood block",
    "Tambourine",
    "Rattle (instrument)",
    "Maraca",
    "Synthesizer",
    "Electronic music",
    "House music",
    "Hip hop music",
    "Electronic dance music",
    "Swing music",
    "Music of Africa",
}


def _windows(audio: np.ndarray, sample_rate: int, window_seconds: float, hop_seconds: float) -> tuple[np.ndarray, list[tuple[float, float]]]:
    window = max(1, int(round(window_seconds * sample_rate)))
    hop = max(1, int(round(hop_seconds * sample_rate)))
    if len(audio) <= window:
        padded = np.pad(audio, (0, max(0, window - len(audio))))
        return padded[None, :].astype(np.float32), [(0.0, len(audio) / sample_rate)]
    starts = list(range(0, len(audio) - window + 1, hop))
    if starts[-1] + window < len(audio):
        starts.append(len(audio) - window)
    clips = np.stack([audio[start:start + window] for start in starts]).astype(np.float32)
    ranges = [(start / sample_rate, min(len(audio), start + window) / sample_rate) for start in starts]
    return clips, ranges


def infer(
    audio_path: str,
    checkpoint_path: str,
    *,
    device: str = "cpu",
    window_seconds: float = 4.0,
    hop_seconds: float = 2.0,
    minimum_score: float = 0.10,
    batch_size: int = 8,
) -> dict:
    from panns_inference import AudioTagging
    from panns_inference.config import labels

    audio, sample_rate = librosa.load(audio_path, sr=32000, mono=True)
    clips, ranges = _windows(audio, sample_rate, window_seconds, hop_seconds)
    # The third-party wrapper prints checkpoint messages to stdout.  Keep
    # stdout machine-readable and send diagnostics to stderr instead.
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        model = AudioTagging(checkpoint_path=checkpoint_path, device=device)
    if captured.getvalue():
        print(captured.getvalue().strip(), file=sys.stderr)

    label_indices = {label: labels.index(label) for label in RELEVANT_LABELS if label in labels}
    predictions = []
    with contextlib.redirect_stdout(captured):
        for start in range(0, len(clips), batch_size):
            output, _embedding = model.inference(clips[start:start + batch_size])
            predictions.append(output)
    scores = np.concatenate(predictions, axis=0) if predictions else np.zeros((0, len(labels)))
    tags = []
    for label, index in label_indices.items():
        if not len(scores):
            continue
        label_scores = scores[:, index]
        best_indices = np.where(label_scores >= minimum_score)[0]
        for window_index in best_indices:
            start, end = ranges[int(window_index)]
            tags.append({
                "label": label,
                "score": round(float(label_scores[window_index]), 5),
                "start": round(float(start), 3),
                "end": round(float(end), 3),
            })
    tags.sort(key=lambda item: (-item["score"], item["start"], item["label"]))
    return {
        "engine": "panns_cnn14_audioset",
        "model": "Cnn14_mAP=0.431",
        "license": "MIT-code; verify-model-and-dataset-terms-for-deployment",
        "audio": os.path.basename(audio_path),
        "window_seconds": window_seconds,
        "hop_seconds": hop_seconds,
        "tags": tags[:1200],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument(
        "--checkpoint",
        default=os.getenv("PANN_CHECKPOINT", str(Path(__file__).resolve().parents[1] / "_external/models/panns/Cnn14_mAP=0.431.pth")),
    )
    parser.add_argument("--device", default=os.getenv("PANN_DEVICE", "cpu"))
    parser.add_argument("--window", type=float, default=4.0)
    parser.add_argument("--hop", type=float, default=2.0)
    parser.add_argument("--minimum-score", type=float, default=0.10)
    args = parser.parse_args()
    result = infer(
        args.audio,
        args.checkpoint,
        device=args.device,
        window_seconds=args.window,
        hop_seconds=args.hop,
        minimum_score=args.minimum_score,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
