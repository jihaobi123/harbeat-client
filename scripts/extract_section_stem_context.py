#!/usr/bin/env python3
"""Extract section-aligned vocal and stem evidence with Demucs.

This is an offline experiment for the relabeler.  It reuses the separator that
HarBeat already runs in production and never changes SongFormer boundaries.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import librosa
import numpy as np
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.section_relabel_dataset import track_is_excluded


MODEL_NAME = "htdemucs"
HOP_LENGTH = 1_024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", default="development")
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    return parser.parse_args()


def _summary(values: np.ndarray) -> np.ndarray:
    if values.ndim == 1:
        values = values[None, :]
    return np.concatenate((np.mean(values, axis=1), np.std(values, axis=1)))


def _slice(start: float, end: float, sr: int, frames: int) -> slice:
    first = max(0, min(frames - 1, int(np.floor(start * sr / HOP_LENGTH))))
    last = max(first + 1, min(frames, int(np.ceil(end * sr / HOP_LENGTH))))
    return slice(first, last)


def separate(
    audio_path: Path, model: torch.nn.Module, *, device: str
) -> tuple[dict[str, np.ndarray], int]:
    sr = int(model.samplerate)
    audio, _ = librosa.load(audio_path, sr=sr, mono=True)
    waveform = torch.from_numpy(audio).float()[None, :].repeat(2, 1)[None, :]
    with torch.inference_mode():
        separated = apply_model(
            model,
            waveform,
            device=device,
            split=True,
            overlap=0.25,
            progress=False,
        )[0]
    return {
        str(name): separated[index].mean(dim=0).cpu().numpy()
        for index, name in enumerate(model.sources)
    }, sr


def extract(stems: dict[str, np.ndarray], sr: int, segments: list[dict]) -> np.ndarray:
    frame_features: dict[str, list[np.ndarray]] = {}
    for name in ("drums", "bass", "other", "vocals"):
        audio = stems[name]
        magnitude = np.abs(librosa.stft(audio, n_fft=2_048, hop_length=HOP_LENGTH))
        power = magnitude**2
        frame_features[name] = [
            librosa.feature.rms(S=magnitude),
            librosa.onset.onset_strength(
                S=librosa.power_to_db(power + 1e-10), sr=sr, hop_length=HOP_LENGTH
            )[None, :],
            librosa.power_to_db(
                librosa.feature.melspectrogram(S=power, sr=sr, n_mels=16) + 1e-10,
                ref=np.max,
            ),
        ]
        if name == "vocals":
            frame_features[name].extend(
                [
                    librosa.feature.mfcc(S=frame_features[name][2], n_mfcc=20),
                    librosa.feature.chroma_stft(S=power, sr=sr),
                ]
            )
    frame_count = min(matrix.shape[1] for values in frame_features.values() for matrix in values)
    track_rms = {
        name: float(np.sqrt(np.mean(np.square(audio))) + 1e-10)
        for name, audio in stems.items()
    }
    total_rms = sum(track_rms.values())
    rows: list[np.ndarray] = []
    for segment in segments:
        start = max(0.0, float(segment.get("start", 0.0) or 0.0))
        end = max(start, float(segment.get("end", start) or start))
        selected = _slice(start, end, sr, frame_count)
        vector: list[np.ndarray] = []
        segment_rms: list[float] = []
        for name in ("drums", "bass", "other", "vocals"):
            matrices = frame_features[name]
            vector.extend(_summary(matrix[:, :frame_count][:, selected]) for matrix in matrices)
            segment_rms.append(float(np.mean(matrices[0][:, :frame_count][:, selected])))
        segment_total = sum(segment_rms) + 1e-10
        vector.append(np.asarray([value / segment_total for value in segment_rms]))
        vector.append(np.asarray([track_rms[name] / total_rms for name in ("drums", "bass", "other", "vocals")]))
        rows.append(np.concatenate(vector))
    return np.vstack(rows).astype(np.float32)


def main() -> int:
    args = parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("invalid shard selection")
    payload = json.loads(args.dataset.expanduser().resolve().read_text(encoding="utf-8"))
    model = get_model(MODEL_NAME).to(args.device)
    model.eval()
    features: list[np.ndarray] = []
    track_ids: list[str] = []
    segment_indices: list[int] = []
    failures: list[dict[str, str]] = []
    selected_tracks = [
        track
        for track in payload.get("tracks") or []
        if track.get("split") == args.split and not track_is_excluded(track)
    ][args.shard_index :: args.shard_count]
    for track in selected_tracks:
        segments = list(track.get("segments") or [])
        try:
            stems, sr = separate(
                Path(str(track.get("audio_path"))), model, device=args.device
            )
            values = extract(stems, sr, segments)
        except Exception as exc:
            failures.append({"track_id": str(track.get("track_id")), "error": str(exc)})
            continue
        features.append(values)
        track_ids.extend([str(track.get("track_id"))] * len(segments))
        segment_indices.extend(range(len(segments)))
        print(f"extracted {track.get('display_name') or track.get('title')}: {len(segments)} segments", flush=True)
    if not features:
        raise SystemExit("no stem context was extracted")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        features=np.vstack(features),
        track_ids=np.asarray(track_ids),
        segment_indices=np.asarray(segment_indices, dtype=np.int64),
        failures=np.asarray([json.dumps(item, ensure_ascii=False) for item in failures]),
    )
    print(json.dumps({"output": str(args.output), "segments": len(track_ids), "failures": failures}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
