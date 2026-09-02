#!/usr/bin/env python3
"""Extract deterministic, boundary-aligned audio context for section relabeling.

The extractor deliberately uses inexpensive DSP features rather than labels or
external metadata.  Every feature is pooled inside an existing SongFormer
segment, so it cannot move a section boundary or leak annotations into model
inputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import librosa
import numpy as np


SAMPLE_RATE = 16_000
HOP_LENGTH = 512
N_FFT = 2_048
MEL_BANDS = 32
MFCC_COUNT = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _summary(values: np.ndarray) -> np.ndarray:
    """Pool a [features, frames] matrix without depending on segment length."""
    if values.ndim == 1:
        values = values[None, :]
    return np.concatenate(
        (
            np.mean(values, axis=1),
            np.std(values, axis=1),
            np.quantile(values, 0.10, axis=1),
            np.quantile(values, 0.90, axis=1),
        )
    )


def _frame_slice(start: float, end: float, frame_count: int) -> slice:
    first = max(0, min(frame_count - 1, int(np.floor(start * SAMPLE_RATE / HOP_LENGTH))))
    last = max(first + 1, min(frame_count, int(np.ceil(end * SAMPLE_RATE / HOP_LENGTH))))
    return slice(first, last)


def extract_track(audio_path: Path, segments: list[dict[str, Any]]) -> np.ndarray:
    audio, _ = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)
    stft = librosa.stft(audio, n_fft=N_FFT, hop_length=HOP_LENGTH)
    magnitude = np.abs(stft)
    power = magnitude**2
    mel = librosa.feature.melspectrogram(
        S=power,
        sr=SAMPLE_RATE,
        n_mels=MEL_BANDS,
        fmin=30.0,
        fmax=SAMPLE_RATE / 2.0,
    )
    log_mel = librosa.power_to_db(mel + 1e-10, ref=np.max)
    mfcc = librosa.feature.mfcc(S=log_mel, n_mfcc=MFCC_COUNT)
    chroma = librosa.feature.chroma_stft(S=power, sr=SAMPLE_RATE, n_fft=N_FFT)
    contrast = librosa.feature.spectral_contrast(S=magnitude, sr=SAMPLE_RATE)
    scalar = np.vstack(
        (
            librosa.feature.rms(S=magnitude),
            librosa.feature.spectral_centroid(S=magnitude, sr=SAMPLE_RATE),
            librosa.feature.spectral_bandwidth(S=magnitude, sr=SAMPLE_RATE),
            librosa.feature.spectral_rolloff(S=magnitude, sr=SAMPLE_RATE),
            librosa.feature.spectral_flatness(S=magnitude),
            librosa.feature.zero_crossing_rate(audio, frame_length=N_FFT, hop_length=HOP_LENGTH),
            librosa.onset.onset_strength(S=librosa.power_to_db(power + 1e-10), sr=SAMPLE_RATE, hop_length=HOP_LENGTH)[None, :],
        )
    )
    frame_count = min(
        log_mel.shape[1], mfcc.shape[1], chroma.shape[1], contrast.shape[1], scalar.shape[1]
    )
    matrices = [
        log_mel[:, :frame_count],
        mfcc[:, :frame_count],
        chroma[:, :frame_count],
        contrast[:, :frame_count],
        scalar[:, :frame_count],
    ]
    rows: list[np.ndarray] = []
    for segment in segments:
        start = max(0.0, float(segment.get("start", 0.0) or 0.0))
        end = max(start, float(segment.get("end", start) or start))
        selected = _frame_slice(start, end, frame_count)
        pooled = np.concatenate([_summary(matrix[:, selected]) for matrix in matrices])
        rows.append(pooled)
    return np.vstack(rows).astype(np.float32)


def main() -> int:
    args = parse_args()
    payload = json.loads(args.dataset.expanduser().resolve().read_text(encoding="utf-8"))
    embeddings: list[np.ndarray] = []
    track_ids: list[str] = []
    segment_indices: list[int] = []
    failures: list[dict[str, str]] = []
    for track in payload.get("tracks") or []:
        segments = list(track.get("segments") or [])
        if not segments:
            continue
        audio_path = Path(str(track.get("audio_path") or "")).expanduser()
        try:
            values = extract_track(audio_path, segments)
        except Exception as exc:  # one corrupt song must not discard the cache
            failures.append({"track_id": str(track.get("track_id")), "error": str(exc)})
            continue
        embeddings.append(values)
        track_ids.extend([str(track.get("track_id"))] * len(segments))
        segment_indices.extend(range(len(segments)))
        print(f"extracted {track.get('display_name') or track.get('title')}: {len(segments)} segments")
    if not embeddings:
        raise SystemExit("no audio features were extracted")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        features=np.vstack(embeddings),
        track_ids=np.asarray(track_ids),
        segment_indices=np.asarray(segment_indices, dtype=np.int64),
        sample_rate=np.asarray(SAMPLE_RATE),
        hop_length=np.asarray(HOP_LENGTH),
        failures=np.asarray([json.dumps(item, ensure_ascii=False) for item in failures]),
    )
    print(json.dumps({"output": str(args.output), "segments": len(track_ids), "failures": failures}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
