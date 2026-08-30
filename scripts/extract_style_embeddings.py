#!/usr/bin/env python3
"""Build beat-aligned segments and extract Discogs-EffNet embeddings.

The script is deliberately checkpointed per track.  It also emits a compact
technical-feature route from the same audio windows so that embedding-only,
technical-only and fusion models can be compared without any filename or
artist metadata entering the model inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.analysis import analyze_audio_file


SAMPLE_RATE = 16_000
EMBEDDING_OUTPUT = "PartitionedCall:1"
MIN_FIXED_WINDOW_SECONDS = 18.0


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
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
        json.dumps(_json_value(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_json_value(row), ensure_ascii=False) + "\n")
    temporary.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        cooked = float(value)
    except (TypeError, ValueError):
        return default
    return cooked if math.isfinite(cooked) else default


def _downbeat_windows(core: dict[str, Any], duration: float) -> tuple[list[tuple[float, float]], list[str]]:
    flags: list[str] = []
    downbeats = np.asarray(core.get("downbeats") or [], dtype=float)
    downbeats = downbeats[np.isfinite(downbeats)]
    downbeats = np.unique(downbeats[(downbeats >= 0.0) & (downbeats <= duration)])
    beat_confidence = _finite(core.get("beat_confidence"))
    time_signature = core.get("time_signature") or {}
    downbeat_consensus = time_signature.get("downbeat_consensus") or {}
    needs_review = bool(
        core.get("beat_needs_review")
        or time_signature.get("needs_review")
        or downbeat_consensus.get("needs_review")
    )
    intervals = np.diff(downbeats)
    median_bar = float(np.median(intervals)) if intervals.size else 0.0
    relative_mad = (
        float(np.median(np.abs(intervals - median_bar))) / median_bar
        if median_bar > 0.0 else float("inf")
    )
    reliable = bool(
        len(downbeats) >= 17
        and beat_confidence >= 0.72
        and not needs_review
        and 0.75 <= median_bar <= 6.0
        and relative_mad <= 0.18
    )
    if not reliable:
        if len(downbeats) < 17:
            flags.append("insufficient_downbeats")
        if beat_confidence < 0.72:
            flags.append("low_beat_confidence")
        if needs_review:
            flags.append("downbeat_needs_review")
        if not 0.75 <= median_bar <= 6.0:
            flags.append("implausible_bar_duration")
        if relative_mad > 0.18:
            flags.append("unstable_bar_duration")
        return [], flags
    windows = [
        (float(downbeats[index]), float(downbeats[index + 16]))
        for index in range(0, len(downbeats) - 16, 8)
        if float(downbeats[index + 16] - downbeats[index]) >= MIN_FIXED_WINDOW_SECONDS
    ]
    if not windows:
        flags.append("beat_windows_too_short")
    return windows, flags


def _fixed_windows(duration: float) -> list[tuple[float, float]]:
    if duration <= 30.0:
        return [(0.0, duration)] if duration >= MIN_FIXED_WINDOW_SECONDS else []
    starts = list(np.arange(0.0, max(0.0, duration - 30.0) + 1e-6, 15.0))
    tail_start = max(0.0, duration - 30.0)
    if not starts or tail_start - starts[-1] >= 7.5:
        starts.append(tail_start)
    return [(float(start), float(min(duration, start + 30.0))) for start in starts]


def _phrase_label(core: dict[str, Any], start: float, end: float) -> str | None:
    best_label = None
    best_overlap = 0.0
    for phrase in core.get("phrase_map") or []:
        if not isinstance(phrase, dict):
            continue
        phrase_start = _finite(phrase.get("start", phrase.get("start_time")), -1.0)
        phrase_end = _finite(phrase.get("end", phrase.get("end_time")), -1.0)
        overlap = max(0.0, min(end, phrase_end) - max(start, phrase_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = str(phrase.get("label") or phrase.get("type") or "unknown")
    return best_label


def _segment_rows(track: dict[str, Any], core: dict[str, Any]) -> list[dict[str, Any]]:
    duration = _finite(core.get("duration"), _finite(track.get("duration_seconds")))
    beat_windows, flags = _downbeat_windows(core, duration)
    method = "beat_aligned_16_bars_hop_8"
    windows = beat_windows
    if not windows:
        method = "fixed_30s_hop_15s"
        windows = _fixed_windows(duration)
        flags = sorted(set(flags + ["unaligned_window"]))
    rows = []
    for index, (start, end) in enumerate(windows):
        rows.append({
            "segment_id": f"{track['track_id']}_s{index:03d}",
            "track_id": track["track_id"],
            "primary_style": track["primary_style"],
            "fold": int(track["fold"]),
            "start_seconds": round(start, 6),
            "end_seconds": round(end, 6),
            "duration_seconds": round(end - start, 6),
            "window_method": method,
            "window_quality_flags": flags,
            "structural_label": _phrase_label(core, start, end),
            "structural_neutral": False,
            "purity_status": "unreviewed",
            "purity_source": None,
        })
    return rows


def _tempo_variation(core: dict[str, Any]) -> float:
    values = []
    for item in core.get("bpm_curve") or []:
        if isinstance(item, dict):
            value = item.get("bpm", item.get("value"))
        else:
            value = item
        cooked = _finite(value, -1.0)
        if cooked > 0:
            values.append(cooked)
    if len(values) < 2:
        return 0.0
    mean = float(np.mean(values))
    return float(np.std(values) / mean) if mean > 0 else 0.0


def _technical_schema() -> list[str]:
    return [
        "track_log2_bpm", "track_beat_confidence", "track_tempo_cv",
        "track_energy", "track_danceability", "meter_3", "meter_4",
        "segment_duration", "rms_mean", "rms_std", "rms_dynamic",
        "crest_factor", "zcr_mean", "zcr_std", "centroid_mean",
        "centroid_std", "bandwidth_mean", "bandwidth_std", "rolloff_mean",
        "rolloff_std", "flatness_mean", "flatness_std", "chroma_entropy",
        *[f"chroma_{index}" for index in range(12)],
        *[f"contrast_{index}" for index in range(7)],
        "onset_mean", "onset_std", "onset_p90",
        *[f"pulse_phase_{index}" for index in range(16)],
        "band_sub", "band_bass", "band_mid", "band_high",
    ]


def _technical_features(audio: np.ndarray, core: dict[str, Any]) -> tuple[np.ndarray, dict[str, float]]:
    import librosa

    eps = 1e-10
    hop = 512
    if audio.size < SAMPLE_RATE:
        audio = np.pad(audio, (0, SAMPLE_RATE - audio.size))
    stft = np.abs(librosa.stft(audio, n_fft=2048, hop_length=hop))
    power = np.square(stft)
    rms = librosa.feature.rms(S=stft)[0]
    zcr = librosa.feature.zero_crossing_rate(audio, frame_length=2048, hop_length=hop)[0]
    centroid = librosa.feature.spectral_centroid(S=stft, sr=SAMPLE_RATE)[0] / (SAMPLE_RATE / 2.0)
    bandwidth = librosa.feature.spectral_bandwidth(S=stft, sr=SAMPLE_RATE)[0] / (SAMPLE_RATE / 2.0)
    rolloff = librosa.feature.spectral_rolloff(S=stft, sr=SAMPLE_RATE, roll_percent=0.85)[0] / (SAMPLE_RATE / 2.0)
    flatness = librosa.feature.spectral_flatness(S=stft)[0]
    chroma = librosa.feature.chroma_stft(S=power, sr=SAMPLE_RATE)
    chroma_mean = np.mean(chroma, axis=1)
    chroma_distribution = chroma_mean / (float(np.sum(chroma_mean)) + eps)
    chroma_entropy = -float(np.sum(chroma_distribution * np.log(chroma_distribution + eps))) / math.log(12.0)
    try:
        contrast = librosa.feature.spectral_contrast(S=stft, sr=SAMPLE_RATE, fmin=100.0)
        contrast_mean = np.mean(contrast, axis=1) / 60.0
    except Exception:
        contrast_mean = np.zeros(7, dtype=float)
    onset = librosa.onset.onset_strength(S=power, sr=SAMPLE_RATE, hop_length=hop)
    pulse_phase = np.zeros(16, dtype=float)
    if onset.size:
        beat_period = 60.0 / max(_finite(core.get("bpm")), 1e-6)
        frame_times = librosa.frames_to_time(
            np.arange(onset.size), sr=SAMPLE_RATE, hop_length=hop,
        )
        phase_bins = np.floor(np.mod(frame_times, beat_period) / beat_period * 16).astype(int)
        for index in range(16):
            part = onset[phase_bins == index]
            pulse_phase[index] = float(np.mean(part)) if part.size else 0.0
        pulse_phase /= float(np.sum(pulse_phase)) + eps
    frequencies = librosa.fft_frequencies(sr=SAMPLE_RATE, n_fft=2048)
    total_power = float(np.sum(power)) + eps
    bands = []
    for lower, upper in ((20, 80), (80, 250), (250, 2000), (2000, 8000)):
        mask = (frequencies >= lower) & (frequencies < upper)
        bands.append(float(np.sum(power[mask])) / total_power)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    signal_rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    meter = int(_finite((core.get("time_signature") or {}).get("numerator"), 0))
    bpm = max(_finite(core.get("bpm")), 1e-6)
    values = [
        math.log2(bpm), _finite(core.get("beat_confidence")), _tempo_variation(core),
        _finite(core.get("energy")), _finite(core.get("danceability_score")),
        float(meter == 3), float(meter == 4), audio.size / SAMPLE_RATE,
        float(np.mean(rms)), float(np.std(rms)),
        float(np.percentile(rms, 90) - np.percentile(rms, 10)),
        peak / (signal_rms + eps), float(np.mean(zcr)), float(np.std(zcr)),
        float(np.mean(centroid)), float(np.std(centroid)),
        float(np.mean(bandwidth)), float(np.std(bandwidth)),
        float(np.mean(rolloff)), float(np.std(rolloff)),
        float(np.mean(flatness)), float(np.std(flatness)), chroma_entropy,
        *chroma_distribution.tolist(), *contrast_mean.tolist(),
        float(np.mean(onset)) if onset.size else 0.0,
        float(np.std(onset)) if onset.size else 0.0,
        float(np.percentile(onset, 90)) if onset.size else 0.0,
        *pulse_phase.tolist(), *bands,
    ]
    diagnostics = {
        "rms_dbfs": 20.0 * math.log10(signal_rms + eps),
        "onset_mean": float(np.mean(onset)) if onset.size else 0.0,
        "flatness_mean": float(np.mean(flatness)),
    }
    vector = np.nan_to_num(np.asarray(values, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    expected = len(_technical_schema())
    if vector.shape != (expected,):
        raise RuntimeError(f"technical feature shape {vector.shape} != {(expected,)}")
    return vector, diagnostics


def _load_audio(path: Path) -> np.ndarray:
    import essentia.standard as es

    return np.asarray(es.MonoLoader(
        filename=str(path), sampleRate=SAMPLE_RATE, resampleQuality=4,
    )(), dtype=np.float32)


def _embedding_frames(predictor: Any, audio: np.ndarray) -> np.ndarray:
    frames = np.asarray(predictor(audio), dtype=np.float32)
    if frames.ndim != 2 or frames.shape[1] != 1280:
        raise RuntimeError(f"unexpected embedding shape: {frames.shape}")
    return np.nan_to_num(frames, nan=0.0, posinf=0.0, neginf=0.0)


def _track_payload(
    track: dict[str, Any], core: dict[str, Any], predictor: Any,
) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray]:
    audio = _load_audio(Path(track["audio_path"]))
    rows = _segment_rows(track, core)
    all_embedding_frames = _embedding_frames(predictor, audio)
    track_duration = audio.size / SAMPLE_RATE
    frame_centers = (
        (np.arange(all_embedding_frames.shape[0], dtype=float) + 0.5)
        * track_duration / all_embedding_frames.shape[0]
    )
    embeddings = []
    technical = []
    for row in rows:
        start_sample = int(round(row["start_seconds"] * SAMPLE_RATE))
        end_sample = min(audio.size, int(round(row["end_seconds"] * SAMPLE_RATE)))
        window = audio[start_sample:end_sample]
        vector, diagnostics = _technical_features(window, core)
        row.update(diagnostics)
        low_information_structure = str(row.get("structural_label") or "").casefold() in {
            "intro", "outro", "breakdown", "break", "transition",
        }
        row["structural_neutral"] = bool(
            low_information_structure
            or diagnostics["rms_dbfs"] < -38.0
            or diagnostics["onset_mean"] < 0.05
        )
        row["structural_neutral_reason"] = (
            "low_information_structure" if low_information_structure
            else "low_rms" if diagnostics["rms_dbfs"] < -38.0
            else "low_onset_activity" if diagnostics["onset_mean"] < 0.05
            else None
        )
        technical.append(vector)
        selected_frames = all_embedding_frames[
            (frame_centers >= row["start_seconds"])
            & (frame_centers < row["end_seconds"])
        ]
        if selected_frames.size == 0:
            nearest = int(np.argmin(np.abs(frame_centers - (row["start_seconds"] + row["end_seconds"]) / 2.0)))
            selected_frames = all_embedding_frames[nearest : nearest + 1]
        embeddings.append(np.mean(selected_frames, axis=0))
    if not rows:
        raise RuntimeError("track yielded no usable segments")
    return rows, np.stack(embeddings), np.stack(technical)


def _consolidate(output_dir: Path, manifest: list[dict[str, Any]]) -> tuple[int, int]:
    rows: list[dict[str, Any]] = []
    embeddings = []
    technical = []
    for track in manifest:
        path = output_dir / "embeddings" / "tracks" / f"{track['track_id']}.npz"
        metadata_path = output_dir / "analysis" / "segments" / f"{track['track_id']}.json"
        if not path.is_file() or not metadata_path.is_file():
            continue
        payload = np.load(path, allow_pickle=False)
        track_rows = json.loads(metadata_path.read_text(encoding="utf-8"))["segments"]
        if len(track_rows) != len(payload["embeddings"]):
            raise RuntimeError(f"checkpoint mismatch for {track['track_id']}")
        rows.extend(track_rows)
        embeddings.append(payload["embeddings"])
        technical.append(payload["technical"])
    if not rows:
        return 0, 0
    ids = np.asarray([row["segment_id"] for row in rows])
    temporary = output_dir / "embeddings" / "segment_features.tmp.npz"
    np.savez_compressed(
        temporary,
        segment_ids=ids,
        embeddings=np.concatenate(embeddings).astype(np.float32),
        technical=np.concatenate(technical).astype(np.float32),
    )
    temporary.replace(output_dir / "embeddings" / "segment_features.npz")
    _atomic_jsonl(output_dir / "segment_manifest.jsonl", rows)
    return len(rows), len({row["track_id"] for row in rows})


def _load_predictor(model_path: Path) -> Any:
    import essentia.standard as es

    return es.TensorflowPredictEffnetDiscogs(
        graphFilename=str(model_path), output=EMBEDDING_OUTPUT,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--track-id", action="append", default=[])
    parser.add_argument("--refresh-features", action="store_true")
    args = parser.parse_args()
    dataset_dir = args.dataset_dir.resolve()
    manifest_path = dataset_dir / "manifest.jsonl"
    if not manifest_path.is_file():
        parser.error(f"manifest not found: {manifest_path}")
    if not args.model.is_file():
        parser.error(f"Discogs-EffNet model not found: {args.model}")
    manifest = _read_jsonl(manifest_path)
    selected = manifest
    if args.track_id:
        requested = set(args.track_id)
        selected = [track for track in selected if track["track_id"] in requested]
        missing = requested - {track["track_id"] for track in selected}
        if missing:
            parser.error(f"unknown track id(s): {', '.join(sorted(missing))}")
    if args.limit > 0:
        selected = selected[: args.limit]
    for directory in (
        dataset_dir / "analysis" / "core",
        dataset_dir / "analysis" / "segments",
        dataset_dir / "embeddings" / "tracks",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    _atomic_json(dataset_dir / "feature_schema.json", {
        "version": "style_reference_features_v1",
        "embedding": {
            "model": "discogs-effnet-bs64-1.pb",
            "model_sha256": _sha256(args.model.resolve()),
            "output": EMBEDDING_OUTPUT,
            "dimension": 1280,
            "aggregation": "mean_over_model_frames_per_segment",
            "sample_rate": SAMPLE_RATE,
        },
        "technical": {
            "dimension": len(_technical_schema()),
            "names": _technical_schema(),
            "source": "audio_only_no_filename_artist_or_folder_inputs",
        },
    })
    predictor = _load_predictor(args.model.resolve())
    errors = []
    for index, track in enumerate(selected, start=1):
        track_id = track["track_id"]
        checkpoint = dataset_dir / "embeddings" / "tracks" / f"{track_id}.npz"
        segments_path = dataset_dir / "analysis" / "segments" / f"{track_id}.json"
        if args.resume and not args.refresh_features and checkpoint.is_file() and segments_path.is_file():
            print(f"[{index}/{len(selected)}] skip completed {track_id}", flush=True)
            continue
        started = time.monotonic()
        try:
            core_path = dataset_dir / "analysis" / "core" / f"{track_id}.json"
            if args.resume and core_path.is_file():
                core = json.loads(core_path.read_text(encoding="utf-8"))
            else:
                core = analyze_audio_file(str(track["audio_path"]))
                _atomic_json(core_path, core)
            rows, embeddings, technical = _track_payload(track, core, predictor)
            temporary = checkpoint.with_suffix(".tmp.npz")
            np.savez_compressed(
                temporary,
                segment_ids=np.asarray([row["segment_id"] for row in rows]),
                embeddings=embeddings.astype(np.float32),
                technical=technical.astype(np.float32),
            )
            temporary.replace(checkpoint)
            _atomic_json(segments_path, {
                "track_id": track_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "segments": rows,
            })
            print(
                f"[{index}/{len(selected)}] {track_id}: {len(rows)} segments, "
                f"{rows[0]['window_method']}, {time.monotonic() - started:.1f}s",
                flush=True,
            )
        except Exception as exc:
            errors.append({"track_id": track_id, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[{index}/{len(selected)}] ERROR {track_id}: {errors[-1]['error']}", flush=True)
        _atomic_json(dataset_dir / "analysis" / "extraction_status.json", {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "selected_tracks": len(selected),
            "errors": errors,
        })
    segment_count, track_count = _consolidate(dataset_dir, manifest)
    methods = Counter()
    if (dataset_dir / "segment_manifest.jsonl").is_file():
        methods.update(row["window_method"] for row in _read_jsonl(dataset_dir / "segment_manifest.jsonl"))
    print(json.dumps({
        "status": "ready" if not errors else "partial",
        "tracks": track_count,
        "segments": segment_count,
        "window_methods": methods,
        "errors": errors,
    }, ensure_ascii=False, default=dict), flush=True)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
