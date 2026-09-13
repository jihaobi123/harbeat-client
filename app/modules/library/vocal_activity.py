"""Versioned Silero markers on published Demucs vocals; never mutate base runs."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import metadata, resources
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .same_style_preprocess import _atomic_json, _json_bytes, _sha256, _track_lock, _utc_now

IMPLEMENTATION = "silero_vocal_activity_v1"


@dataclass(frozen=True)
class VocalConfig:
    threshold: float = 0.5
    neg_threshold: float = 0.35
    min_speech_duration_ms: int = 250
    min_silence_duration_ms: int = 300
    speech_pad_ms: int = 100
    sampling_rate: int = 16000


def storage_path(root: Path, key: str) -> Path:
    if not isinstance(key, str) or not key or Path(key).is_absolute() or ".." in Path(key).parts:
        raise ValueError("invalid storage key")
    path = (root / key).resolve()
    path.relative_to(root.resolve())
    return path


def sample_intervals(timestamps: list[dict], duration_ms: int, rate: int = 16000) -> list[dict]:
    """Half-open integer-ms intervals, clamped, sorted and non-overlapping."""
    result: list[dict] = []
    spans = sorted((max(0, round(t["start"] * 1000 / rate)),
                    min(duration_ms, round(t["end"] * 1000 / rate))) for t in timestamps)
    for start, end in spans:
        if end <= start:
            continue
        if result and start <= result[-1]["end_ms"]:
            result[-1]["end_ms"] = max(end, result[-1]["end_ms"])
        else:
            result.append({"start_ms": start, "end_ms": end})
    return result


class SileroDetector:
    """CPU TorchScript, bundled offline weights; no change to CUDA dependencies."""

    def __init__(self, config: VocalConfig | None = None):
        import torch
        from silero_vad import load_silero_vad

        self.config = config or VocalConfig()
        torch.set_num_threads(1)
        self.model = load_silero_vad(onnx=False)
        weight = resources.files("silero_vad.data").joinpath("silero_vad.jit")
        self.provenance = {
            "implementation": IMPLEMENTATION,
            "model": "silero_vad",
            "package_version": metadata.version("silero-vad"),
            "model_sha256": hashlib.sha256(weight.read_bytes()).hexdigest(),
            "backend": "torchscript_cpu",
            "torch_version": torch.__version__,
            "parameters": asdict(self.config),
            "resampling": "scipy.signal.resample_poly",
            "channel_reduction": "arithmetic_mean",
        }

    def detect(self, audio: Path) -> tuple[list[dict], int]:
        import numpy as np
        import soundfile as sf
        from scipy.signal import resample_poly
        import torch
        from silero_vad import get_speech_timestamps

        samples, rate = sf.read(audio, dtype="float32", always_2d=True)
        if not len(samples) or not np.isfinite(samples).all():
            raise ValueError("empty or non-finite vocal audio")
        duration_ms = round(len(samples) * 1000 / rate)
        mono = samples.mean(axis=1)
        target = self.config.sampling_rate
        if rate != target:
            factor = math.gcd(rate, target)
            mono = resample_poly(mono, target // factor, rate // factor).astype(np.float32)
        # No per-song loudness normalization: it can amplify Demucs leakage.
        # Sample indices avoid Silero's default 0.1-second rounding.
        with torch.inference_mode():
            timestamps = get_speech_timestamps(
                torch.from_numpy(mono.copy()), self.model,
                return_seconds=False, **asdict(self.config),
            )
        return sample_intervals(timestamps, duration_ms, target), duration_ms


def publish_vocal_activity(root: Path, manifest_key: str, *, detector=None) -> dict[str, Any]:
    """Validate base input, cache by content + model + parameters, publish atomically.

    A failure raises; it MUST NOT be converted to an empty successful interval list.
    The caller records failures independently of the completed base analysis.
    """
    root = root.resolve()
    manifest_path = storage_path(root, manifest_key)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    success = json.loads((manifest_path.parent / "_SUCCESS.json").read_text())
    if success["manifest_sha256"] != manifest_sha or success["analysis_run_id"] != manifest["analysis_run_id"]:
        raise ValueError("base manifest integrity check failed")
    stem = manifest["assets"]["stems"]["vocals"]
    vocal_path = storage_path(root, stem["storage_key"])
    if _sha256(vocal_path) != stem["sha256"]:
        raise ValueError("vocal stem SHA256 mismatch")
    detector = detector or SileroDetector()
    binding = {
        "track_id": manifest["track_id"],
        "analysis_run_id": manifest["analysis_run_id"],
        "manifest_storage_key": manifest_key,
        "manifest_sha256": manifest_sha,
        "vocal_storage_key": stem["storage_key"],
        "vocal_sha256": stem["sha256"],
    }
    identity = {"source": binding, "producer": detector.provenance}
    revision = hashlib.sha256(_json_bytes(identity)).hexdigest()
    base = f"published/vocal_activity/{binding['track_id']}/{binding['analysis_run_id']}"
    report_key = f"{base}/{revision}/vocal_activity.json"
    report_path = storage_path(root, report_key)
    success_path = report_path.parent / "_SUCCESS.json"
    # Separate lock from the base publisher; safe for CLI and backfill together.
    lock_id = "vocal-" + hashlib.sha256(manifest_key.encode()).hexdigest()[:32]
    with _track_lock(root, lock_id, 21600):
        if success_path.is_file():
            marker = json.loads(success_path.read_text())
            if _sha256(report_path) != marker["vocal_activity_sha256"]:
                raise ValueError("published vocal report integrity check failed")
        else:
            intervals, duration_ms = detector.detect(vocal_path)
            if abs(duration_ms - stem["duration_ms"]) > 100:
                raise ValueError("vocal audio duration differs from manifest")
            active_ms = sum(t["end_ms"] - t["start_ms"] for t in intervals)
            payload = {
                "schema_name": "harbeat_vocal_activity", "schema_version": "1.0.0",
                "status": "ready", "generated_at": _utc_now(),
                **identity, "unit": "ms", "time_origin": "master_audio_start",
                "interval_convention": "[start_ms,end_ms)",
                "duration_ms": duration_ms, "intervals": intervals,
                "has_vocals": bool(intervals), "active_duration_ms": active_ms,
                "coverage_ratio": active_ms / duration_ms if duration_ms else 0.0,
                "needs_review": True,
                "quality_flags": ["speech_vad_on_separated_singing_not_accuracy_certified"],
            }
            _atomic_json(report_path, payload)
            _atomic_json(success_path, {"vocal_activity_sha256": _sha256(report_path), "published_at": _utc_now()})
        pointer = {
            "schema_name": "harbeat_vocal_activity_pointer", "schema_version": "1.0.0",
            **binding, "status": "ready", "vocal_activity_storage_key": report_key,
            "vocal_activity_sha256": _sha256(report_path),
        }
        _atomic_json(storage_path(root, f"{base}/latest.json"), pointer)
        return pointer
