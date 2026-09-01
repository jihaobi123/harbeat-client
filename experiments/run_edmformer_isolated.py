"""Run EDMFormer in isolation while preserving its raw six-class probabilities.

The upstream EDM-98 API intentionally returns only postprocessed segments. This
adapter temporarily wraps that package's postprocessor during one prediction so
the exact logits passed into the official postprocessor can also be recorded.
The upstream source tree itself remains unmodified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np


RUNNER_VERSION = "edmformer_isolated_v1"
EDM_LABELS = ("intro", "buildup", "drop", "breakdown", "outro", "silence")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_revision(path: Path) -> str | None:
    marker = path / "REVISION"
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip()[:64]
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()[:64]
    except Exception:
        return None


def capture_raw_logits(
    pipeline: Any, audio_path: str | Path, postprocess_module: Any
) -> tuple[list[dict[str, Any]], Any]:
    original = postprocess_module.postprocess_functional_structure
    captured: dict[str, Any] = {}

    def capture(logits: Any, config: Any):
        captured["logits"] = logits
        return original(logits, config)

    postprocess_module.postprocess_functional_structure = capture
    try:
        prediction = pipeline.predict_file(str(audio_path))
    finally:
        postprocess_module.postprocess_functional_structure = original
    if "logits" not in captured:
        raise RuntimeError("EDM-98 postprocessor did not expose inference logits")
    return prediction, captured["logits"]


def _as_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def six_class_frames(
    function_logits: Any,
    *,
    label_to_id: Mapping[str, int],
    frame_rate: float,
    duration_sec: float,
) -> list[dict[str, Any]]:
    logits = _as_numpy(function_logits)
    if logits.ndim != 3 or logits.shape[0] != 1:
        raise ValueError("EDMFormer function logits must have shape [1, frames, classes]")
    if frame_rate <= 0 or duration_sec <= 0:
        raise ValueError("frame rate and duration must be positive")
    if set(EDM_LABELS) - set(label_to_id):
        raise ValueError("EDMFormer label map is incomplete")
    class_ids = [int(label_to_id[label]) for label in EDM_LABELS]
    selected = logits[0][:, class_ids].astype(np.float64, copy=False)
    selected -= selected.max(axis=1, keepdims=True)
    probabilities = np.exp(selected)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    frames: list[dict[str, Any]] = []
    for index, row in enumerate(probabilities):
        start_sec = index / frame_rate
        if start_sec >= duration_sec:
            break
        end_sec = min(duration_sec, (index + 1) / frame_rate)
        values = {
            label: round(float(row[offset]), 8)
            for offset, label in enumerate(EDM_LABELS)
        }
        top = max(values, key=values.get)
        values[top] = round(values[top] + (1.0 - sum(values.values())), 8)
        frames.append(
            {
                "start_sec": round(start_sec, 6),
                "end_sec": round(end_sec, 6),
                "probabilities": values,
            }
        )
    if not frames:
        raise ValueError("EDMFormer returned no usable frames")
    return frames


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--edm98-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--musicfm-source", type=Path, required=True)
    parser.add_argument("--musicfm-model", type=Path, required=True)
    parser.add_argument("--musicfm-stats", type=Path, required=True)
    parser.add_argument("--muq-model", type=Path, required=True)
    parser.add_argument("--hf-cache-dir", type=Path, required=True)
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    return parser.parse_args()


def _require_files(paths: Sequence[Path]) -> None:
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)


def main() -> int:
    args = parse_args()
    audio = args.audio.expanduser().resolve()
    edm98_root = args.edm98_root.expanduser().resolve()
    checkpoint = args.checkpoint.expanduser().resolve()
    config = args.config.expanduser().resolve()
    musicfm_model = args.musicfm_model.expanduser().resolve()
    musicfm_stats = args.musicfm_stats.expanduser().resolve()
    muq_model = args.muq_model.expanduser().resolve()
    _require_files([audio, checkpoint, config, musicfm_model, musicfm_stats])
    if not (edm98_root / "src/edm98").is_dir():
        raise FileNotFoundError(edm98_root / "src/edm98")
    if not muq_model.is_dir():
        raise FileNotFoundError(muq_model)

    sys.path.insert(0, str(edm98_root / "src"))
    os.environ["MUSICFMPATH"] = str(args.musicfm_source.expanduser().resolve())

    from edm98.inference import pipeline as pipeline_module
    from edm98.inference import postprocess as postprocess_module
    from edm98.inference.labels import LABEL_TO_ID
    import torch

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    original_create_muq = pipeline_module.InferencePipeline._create_muq_model

    def create_local_muq(instance: Any):
        MuQ = pipeline_module._load_muq()
        model = pipeline_module._call_with_optional_kwargs(
            MuQ.from_pretrained,
            str(muq_model),
            local_files_only=True,
        )
        return model.to(instance.device).eval()

    pipeline_module.InferencePipeline._create_muq_model = create_local_muq
    try:
        pipeline = pipeline_module.create_pipeline(
            checkpoint_path=checkpoint,
            config_path=config,
            musicfm_stat_path=musicfm_stats,
            musicfm_model_path=musicfm_model,
            device=args.device,
            low_memory=True,
            persistent_models=False,
            hf_cache_dir=args.hf_cache_dir.expanduser().resolve(),
            offline=True,
        )
        prediction, logits = capture_raw_logits(
            pipeline, audio, postprocess_module
        )
    finally:
        pipeline_module.InferencePipeline._create_muq_model = original_create_muq

    import librosa

    duration_sec = float(librosa.get_duration(path=str(audio)))
    frames = six_class_frames(
        logits["function_logits"],
        label_to_id=LABEL_TO_ID,
        frame_rate=float(pipeline.config.frame_rates),
        duration_sec=duration_sec,
    )
    boundaries = sorted(
        {
            round(float(segment["start"]), 6)
            for segment in prediction
            if 0 < float(segment["start"]) < duration_sec
        }
    )
    peak_cuda_bytes = int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else 0
    manifest = {
        "schema_name": "harbeat.edmformer_runtime_manifest",
        "schema_version": "0.1.0",
        "runtime_fingerprint": {
            "runner_version": RUNNER_VERSION,
            "python": sys.version.split()[0],
            "device": args.device,
            "source_revision": source_revision(edm98_root),
            "probability_capture": "upstream_postprocessor_wrapper_v1",
            "peak_cuda_bytes": peak_cuda_bytes,
        },
        "tracks": [
            {
                "audio_path": str(audio),
                "audio_sha256": sha256_file(audio),
                "duration_sec": round(duration_sec, 6),
                "status": "ready",
                "frames": frames,
                "boundary_candidates": boundaries,
                "muq_sha256": sha256_file(next(muq_model.rglob("*.safetensors"))),
                "musicfm_sha256": sha256_file(musicfm_model),
                "musicfm_stats_sha256": sha256_file(musicfm_stats),
                "edmformer_sha256": sha256_file(checkpoint),
                "warnings": [],
                "error": None,
            }
        ],
    }
    atomic_json(args.output_dir.expanduser().resolve() / "manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
