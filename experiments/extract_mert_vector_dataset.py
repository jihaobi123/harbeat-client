#!/usr/bin/env python3
"""Extract a reusable, frozen MERT-v1-95M vector dataset.

The extractor keeps all 13 hidden-state layers, but pools the native 75 Hz
sequence to a configurable time grid (0.5 s by default).  This preserves a
useful temporal signal without making the cache hundreds of gigabytes.  The
same time grid is then aggregated to the existing HarBeat bar grid and to one
whole-song embedding.  No style or feature head is trained here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import librosa
import numpy as np


SCHEMA_VERSION = "harbeat_mert_vectors_v1"
DEFAULT_MODEL_ID = "m-a-p/MERT-v1-95M"
DEFAULT_REVISION = "12af15f"
EXPECTED_LAYER_COUNT = 13
EXPECTED_HIDDEN_SIZE = 768
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_npz(path: Path, **arrays: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    temporary.replace(path)


def _sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _chunk_starts(duration: float, chunk_sec: float, hop_sec: float) -> list[float]:
    """Return overlapping starts and force one full-context tail window."""
    if duration <= chunk_sec:
        return [0.0]
    starts = list(np.arange(0.0, max(0.0, duration - chunk_sec) + 1e-6, hop_sec))
    tail = max(0.0, duration - chunk_sec)
    if not starts or abs(starts[-1] - tail) > 1e-3:
        starts.append(tail)
    return [round(float(value), 6) for value in starts]


def _time_grid(duration: float, bin_sec: float) -> tuple[np.ndarray, np.ndarray]:
    # Audio decoders can return one extra sample at an otherwise exact bin
    # boundary (for example 113.0000417 s at 24 kHz). Do not create a separate
    # half-second bin for that one-sample tail; include it in the previous bin.
    # 1e-4 s is 2.4 samples at MERT's fixed 24 kHz input rate.
    nearest_boundary = round(duration / bin_sec) * bin_sec
    grid_duration = (
        nearest_boundary
        if abs(duration - nearest_boundary) <= 1e-4
        else duration
    )
    count = max(1, int(np.ceil(grid_duration / bin_sec)))
    starts = np.arange(count, dtype=np.float32) * float(bin_sec)
    ends = np.minimum(starts + float(bin_sec), float(duration)).astype(np.float32)
    ends[-1] = float(duration)
    return starts, ends


def _bar_intervals(
    downbeats: list[float] | np.ndarray,
    duration: float,
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(downbeats, dtype=np.float64)
    values = np.unique(values[np.isfinite(values) & (values >= 0.0) & (values < duration)])
    if not len(values):
        return np.empty(0, dtype=np.float32), np.empty(0, dtype=np.float32)
    starts = values.astype(np.float32)
    ends = np.concatenate([values[1:], np.asarray([duration])]).astype(np.float32)
    valid = ends - starts >= 0.1
    return starts[valid], ends[valid]


def _aggregate_intervals(
    embeddings: np.ndarray,
    bin_starts: np.ndarray,
    bin_ends: np.ndarray,
    interval_starts: np.ndarray,
    interval_ends: np.ndarray,
) -> np.ndarray:
    """Overlap-weight time-grid embeddings into arbitrary intervals."""
    output = np.zeros(
        (len(interval_starts), embeddings.shape[1], embeddings.shape[2]),
        dtype=np.float32,
    )
    for index, (start, end) in enumerate(zip(interval_starts, interval_ends)):
        overlap = np.maximum(
            0.0,
            np.minimum(bin_ends, float(end)) - np.maximum(bin_starts, float(start)),
        ).astype(np.float32)
        total = float(np.sum(overlap))
        if total <= 1e-8:
            center = (float(start) + float(end)) / 2.0
            nearest = int(np.argmin(np.abs((bin_starts + bin_ends) / 2.0 - center)))
            output[index] = embeddings[nearest]
            continue
        output[index] = np.tensordot(overlap / total, embeddings, axes=(0, 0))
    return output


def _quantization_metrics(values: np.ndarray) -> dict[str, float]:
    restored = values.astype(np.float16).astype(np.float32)
    flattened = values.reshape(len(values), -1)
    restored_flat = restored.reshape(len(restored), -1)
    numerator = np.sum(flattened * restored_flat, axis=1)
    denominator = (
        np.linalg.norm(flattened, axis=1) * np.linalg.norm(restored_flat, axis=1)
        + 1e-12
    )
    cosine = numerator / denominator
    return {
        "mean_cosine_float32_vs_float16": round(float(np.mean(cosine)), 8),
        "min_cosine_float32_vs_float16": round(float(np.min(cosine)), 8),
        "max_abs_error": round(float(np.max(np.abs(values - restored))), 8),
    }


def _label_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            str(row["track_id"]): dict(row)
            for row in csv.DictReader(handle)
            if row.get("track_id")
        }


def _discover_tracks(dataset_root: Path) -> list[dict[str, Any]]:
    labels = _label_rows(dataset_root / "label_audit.csv")
    tracks = []
    for audio_path in sorted((dataset_root / "audio").rglob("*")):
        if not audio_path.is_file() or audio_path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            continue
        track_id = audio_path.stem
        label = labels.get(track_id, {})
        tracks.append({
            "track_id": track_id,
            "audio_path": audio_path.resolve(),
            "primary_style": label.get("primary_style") or audio_path.parent.name,
            "artist": label.get("artist") or "",
            "primary_artist": label.get("primary_artist") or "",
            "title": label.get("title") or track_id,
            "original_filename": label.get("original_filename") or audio_path.name,
            "fold": int(label["fold"]) if label.get("fold", "").isdigit() else None,
            "label_status": label.get("label_status") or "unknown",
            "purity_grade": label.get("purity_grade") or "",
            "risk_flags": label.get("risk_flags") or "[]",
        })
    return tracks


def _device(requested: str) -> str:
    import torch

    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load_model(
    model_id: str,
    revision: str,
    cache_dir: Path,
    device: str,
):
    import torch
    from transformers import AutoModel, Wav2Vec2FeatureExtractor

    processor = Wav2Vec2FeatureExtractor.from_pretrained(
        model_id,
        revision=revision,
        trust_remote_code=True,
        cache_dir=str(cache_dir),
    )
    # MERT's published checkpoint stores the legacy ``weight_g/weight_v``
    # keys.  Transformers 4.38 conditionally switches HuBERT positional
    # convolution to the newer parametrization API when a recent Torch makes
    # it available, which silently leaves those published weights unloaded.
    # Force the legacy constructor only while instantiating the model, then
    # restore Torch's module immediately.  The loading-info assertion below
    # turns future compatibility drift into a hard failure.
    parametrizations = torch.nn.utils.parametrizations
    modern_weight_norm = getattr(parametrizations, "weight_norm", None)
    if modern_weight_norm is not None:
        delattr(parametrizations, "weight_norm")
    try:
        model, loading_info = AutoModel.from_pretrained(
            model_id,
            revision=revision,
            trust_remote_code=True,
            cache_dir=str(cache_dir),
            output_loading_info=True,
        )
    finally:
        if modern_weight_norm is not None:
            setattr(parametrizations, "weight_norm", modern_weight_norm)
    missing = list(loading_info.get("missing_keys") or [])
    unexpected = list(loading_info.get("unexpected_keys") or [])
    mismatched = list(loading_info.get("mismatched_keys") or [])
    if missing or unexpected or mismatched:
        raise RuntimeError(
            "MERT checkpoint did not load exactly: "
            f"missing={missing}, unexpected={unexpected}, mismatched={mismatched}"
        )
    model.requires_grad_(False)
    model.eval().to(device)
    resolved_revision = str(getattr(model.config, "_commit_hash", None) or revision)
    return model, processor, resolved_revision, torch


def _extract_time_embeddings(
    audio: np.ndarray,
    sample_rate: int,
    duration: float,
    *,
    model: Any,
    processor: Any,
    torch: Any,
    device: str,
    chunk_sec: float,
    hop_sec: float,
    bin_sec: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    bin_starts, bin_ends = _time_grid(duration, bin_sec)
    accumulator = np.zeros(
        (len(bin_starts), EXPECTED_LAYER_COUNT, EXPECTED_HIDDEN_SIZE),
        dtype=np.float32,
    )
    token_counts = np.zeros(len(bin_starts), dtype=np.uint16)
    chunk_starts = _chunk_starts(duration, chunk_sec, hop_sec)

    for chunk_index, start_sec in enumerate(chunk_starts, start=1):
        start_sample = int(round(start_sec * sample_rate))
        end_sample = min(len(audio), start_sample + int(round(chunk_sec * sample_rate)))
        clip = np.asarray(audio[start_sample:end_sample], dtype=np.float32)
        if len(clip) < max(400, int(0.1 * sample_rate)):
            continue
        clip_duration = len(clip) / sample_rate
        inputs = processor(
            clip,
            sampling_rate=sample_rate,
            return_tensors="pt",
            padding=False,
        )
        inputs = {name: value.to(device) for name, value in inputs.items()}
        with torch.inference_mode():
            outputs = model(**inputs, output_hidden_states=True)
        hidden = torch.stack(outputs.hidden_states, dim=1).squeeze(0)
        if hidden.shape[0] != EXPECTED_LAYER_COUNT or hidden.shape[-1] != EXPECTED_HIDDEN_SIZE:
            raise ValueError(f"Unexpected MERT hidden-state shape: {tuple(hidden.shape)}")
        hidden_np = hidden.detach().float().cpu().numpy()
        token_count = hidden_np.shape[1]
        token_centers = start_sec + (
            (np.arange(token_count, dtype=np.float64) + 0.5) / token_count * clip_duration
        )
        bin_indices = np.floor(token_centers / bin_sec).astype(int)
        bin_indices = np.clip(bin_indices, 0, len(bin_starts) - 1)
        for bin_index in np.unique(bin_indices):
            mask = bin_indices == bin_index
            accumulator[bin_index] += np.sum(hidden_np[:, mask, :], axis=1)
            token_counts[bin_index] += int(np.sum(mask))
        del hidden, hidden_np, inputs, outputs
        print(
            f"    chunk {chunk_index:03d}/{len(chunk_starts):03d} "
            f"{start_sec:7.2f}s tokens={token_count}",
            flush=True,
        )

    if np.any(token_counts == 0):
        missing = np.flatnonzero(token_counts == 0)
        raise ValueError(f"MERT time grid contains {len(missing)} uncovered bins")
    embeddings = accumulator / token_counts[:, None, None].astype(np.float32)
    if not np.all(np.isfinite(embeddings)):
        raise ValueError("MERT produced non-finite embeddings")
    return embeddings, bin_starts, bin_ends, token_counts, len(chunk_starts)


def _cache_record(
    output_path: Path,
    audio_sha256: str,
    *,
    model_id: str,
    requested_revision: str,
    bin_sec: float,
) -> dict[str, Any] | None:
    if not output_path.is_file():
        return None
    try:
        with np.load(output_path, allow_pickle=False) as payload:
            if str(payload["schema_version"]) != SCHEMA_VERSION:
                return None
            if str(payload["audio_sha256"]) != audio_sha256:
                return None
            if str(payload["model_id"]) != model_id:
                return None
            if str(payload["requested_revision"]) != requested_revision:
                return None
            if abs(float(payload["bin_sec"]) - bin_sec) > 1e-7:
                return None
            return {
                "output_path": str(output_path),
                "time_shape": list(payload["time_embeddings"].shape),
                "bar_shape": list(payload["bar_embeddings"].shape),
                "song_shape": list(payload["song_embedding"].shape),
                "duration": float(payload["duration"]),
                "resolved_revision": str(payload["resolved_revision"]),
                "status": "cached",
            }
    except (OSError, KeyError, ValueError):
        return None


def _extract_track(
    track: dict[str, Any],
    dataset_root: Path,
    output_dir: Path,
    *,
    model: Any,
    processor: Any,
    resolved_revision: str,
    torch: Any,
    device: str,
    model_id: str,
    requested_revision: str,
    chunk_sec: float,
    hop_sec: float,
    bin_sec: float,
    audio_sha256: str,
) -> dict[str, Any]:
    audio_path = Path(track["audio_path"])
    output_path = output_dir / "tracks" / f"{track['track_id']}.npz"
    started = time.monotonic()
    sample_rate = int(processor.sampling_rate)
    audio, _ = librosa.load(audio_path, sr=sample_rate, mono=True)
    audio = np.asarray(audio, dtype=np.float32)
    duration = len(audio) / sample_rate
    embeddings, bin_starts, bin_ends, token_counts, chunk_count = (
        _extract_time_embeddings(
            audio,
            sample_rate,
            duration,
            model=model,
            processor=processor,
            torch=torch,
            device=device,
            chunk_sec=chunk_sec,
            hop_sec=hop_sec,
            bin_sec=bin_sec,
        )
    )
    duration_weights = (bin_ends - bin_starts).astype(np.float32)
    song_embedding = np.tensordot(
        duration_weights / np.sum(duration_weights),
        embeddings,
        axes=(0, 0),
    ).astype(np.float32)

    core_path = dataset_root / "analysis" / "core" / f"{track['track_id']}.json"
    core = json.loads(core_path.read_text(encoding="utf-8")) if core_path.is_file() else {}
    bar_starts, bar_ends = _bar_intervals(core.get("downbeats") or [], duration)
    bar_embeddings = _aggregate_intervals(
        embeddings,
        bin_starts,
        bin_ends,
        bar_starts,
        bar_ends,
    )
    quantization = _quantization_metrics(embeddings)

    _atomic_npz(
        output_path,
        schema_version=np.asarray(SCHEMA_VERSION),
        track_id=np.asarray(track["track_id"]),
        primary_style=np.asarray(track["primary_style"]),
        artist=np.asarray(track["artist"]),
        primary_artist=np.asarray(track["primary_artist"]),
        title=np.asarray(track["title"]),
        original_filename=np.asarray(track["original_filename"]),
        fold=np.asarray(-1 if track["fold"] is None else track["fold"], dtype=np.int16),
        audio_path=np.asarray(str(audio_path)),
        audio_sha256=np.asarray(audio_sha256),
        model_id=np.asarray(model_id),
        requested_revision=np.asarray(requested_revision),
        resolved_revision=np.asarray(resolved_revision),
        sample_rate=np.asarray(sample_rate, dtype=np.int32),
        duration=np.asarray(duration, dtype=np.float32),
        native_feature_rate_hz=np.asarray(75.0, dtype=np.float32),
        chunk_sec=np.asarray(chunk_sec, dtype=np.float32),
        hop_sec=np.asarray(hop_sec, dtype=np.float32),
        bin_sec=np.asarray(bin_sec, dtype=np.float32),
        time_starts=bin_starts.astype(np.float32),
        time_ends=bin_ends.astype(np.float32),
        time_token_counts=token_counts,
        time_embeddings=embeddings.astype(np.float16),
        bar_starts=bar_starts.astype(np.float32),
        bar_ends=bar_ends.astype(np.float32),
        bar_embeddings=bar_embeddings.astype(np.float16),
        song_embedding=song_embedding.astype(np.float16),
    )
    return {
        **track,
        "audio_path": str(audio_path),
        "audio_sha256": audio_sha256,
        "output_path": str(output_path),
        "status": "completed",
        "duration": round(duration, 4),
        "sample_rate": sample_rate,
        "chunk_count": chunk_count,
        "time_shape": list(embeddings.shape),
        "bar_shape": list(bar_embeddings.shape),
        "song_shape": list(song_embedding.shape),
        "quantization": quantization,
        "elapsed_sec": round(time.monotonic() - started, 3),
        "resolved_revision": resolved_revision,
    }


def _write_index(output_dir: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "track_id",
        "primary_style",
        "artist",
        "primary_artist",
        "title",
        "original_filename",
        "fold",
        "label_status",
        "purity_grade",
        "status",
        "duration",
        "chunk_count",
        "time_shape",
        "bar_shape",
        "song_shape",
        "output_path",
        "audio_sha256",
    ]
    path = output_dir / "index.csv"
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            for key in ("time_shape", "bar_shape", "song_shape"):
                row[key] = json.dumps(row.get(key), ensure_ascii=False)
            writer.writerow(row)
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--device", choices=("auto", "mps", "cpu", "cuda"), default="auto")
    parser.add_argument("--chunk-sec", type=float, default=5.0)
    parser.add_argument("--hop-sec", type=float, default=2.5)
    parser.add_argument("--bin-sec", type=float, default=0.5)
    parser.add_argument("--track-id", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--hf-cache-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".runtime" / "huggingface",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not (0.1 <= args.bin_sec <= args.hop_sec <= args.chunk_sec):
        raise ValueError("Require 0.1 <= bin_sec <= hop_sec <= chunk_sec")
    dataset_root = args.dataset_root.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else dataset_root / "embeddings" / "mert_v1_95m_v1"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    tracks = _discover_tracks(dataset_root)
    if args.track_id:
        selected = set(args.track_id)
        tracks = [track for track in tracks if track["track_id"] in selected]
    if args.limit is not None:
        tracks = tracks[: max(0, args.limit)]
    if not tracks:
        raise ValueError("No matching audio tracks found")

    print(f"dataset={dataset_root}", flush=True)
    print(f"output={output_dir}", flush=True)
    print(f"tracks={len(tracks)}", flush=True)
    device = _device(args.device)
    records: list[dict[str, Any]] = []
    pending: list[tuple[dict[str, Any], str]] = []
    for track in tracks:
        audio_sha256 = _sha256(Path(track["audio_path"]))
        output_path = output_dir / "tracks" / f"{track['track_id']}.npz"
        cached = None if args.overwrite else _cache_record(
            output_path,
            audio_sha256,
            model_id=args.model_id,
            requested_revision=args.revision,
            bin_sec=args.bin_sec,
        )
        if cached is None:
            pending.append((track, audio_sha256))
        else:
            records.append({
                **track,
                "audio_path": str(track["audio_path"]),
                "audio_sha256": audio_sha256,
                **cached,
            })

    model = processor = torch = None
    resolved_revision = args.revision
    if pending:
        print(f"loading {args.model_id}@{args.revision} on {device}", flush=True)
        model, processor, resolved_revision, torch = _load_model(
            args.model_id,
            args.revision,
            args.hf_cache_dir.expanduser().resolve(),
            device,
        )
        print(f"resolved_revision={resolved_revision}", flush=True)

    errors: list[dict[str, str]] = []
    for index, (track, audio_sha256) in enumerate(pending, start=1):
        print(
            f"[{index}/{len(pending)}] {track['track_id']} "
            f"{track['primary_style']} {track['original_filename']}",
            flush=True,
        )
        try:
            record = _extract_track(
                track,
                dataset_root,
                output_dir,
                model=model,
                processor=processor,
                resolved_revision=resolved_revision,
                torch=torch,
                device=device,
                model_id=args.model_id,
                requested_revision=args.revision,
                chunk_sec=args.chunk_sec,
                hop_sec=args.hop_sec,
                bin_sec=args.bin_sec,
                audio_sha256=audio_sha256,
            )
            records.append(record)
            print(
                f"[{index}/{len(pending)}] done time={record['time_shape']} "
                f"bars={record['bar_shape']} elapsed={record['elapsed_sec']:.1f}s",
                flush=True,
            )
        except Exception as exc:
            error = {
                "track_id": str(track["track_id"]),
                "audio_path": str(track["audio_path"]),
                "error": f"{type(exc).__name__}: {exc}",
            }
            errors.append(error)
            print(f"[{index}/{len(pending)}] ERROR {error['error']}", flush=True)

        records.sort(key=lambda item: str(item["track_id"]))
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dataset_root": str(dataset_root),
            "model": {
                "id": args.model_id,
                "requested_revision": args.revision,
                "resolved_revision": resolved_revision,
                "license": "CC-BY-NC-4.0",
                "frozen": True,
                "native_sample_rate": int(processor.sampling_rate),
                "native_feature_rate_hz": 75.0,
                "hidden_layers_including_projection": EXPECTED_LAYER_COUNT,
                "hidden_size": EXPECTED_HIDDEN_SIZE,
            },
            "extraction": {
                "device": device,
                "chunk_sec": args.chunk_sec,
                "hop_sec": args.hop_sec,
                "time_bin_sec": args.bin_sec,
                "storage_dtype": "float16",
                "time_pooling": "token_mean_with_overlap_averaging",
                "bar_pooling": "time_bin_overlap_weighted_mean",
                "song_pooling": "duration_weighted_time_bin_mean",
            },
            "track_count_requested": len(tracks),
            "track_count_completed": len(records),
            "track_count_failed": len(errors),
            "labels_are_reviewed": False,
            "tracks": records,
            "errors": errors,
        }
        _atomic_json(output_dir / "manifest.json", manifest)
        _write_index(output_dir, records)

    if not pending:
        records.sort(key=lambda item: str(item["track_id"]))
        _write_index(output_dir, records)
        print(f"all {len(records)} selected tracks were cached", flush=True)
    return 0 if not errors else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    raise SystemExit(main())
