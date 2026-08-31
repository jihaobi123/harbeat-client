"""Pure helpers for reproducible SongFormer inference and label evidence."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


RUNNER_VERSION = "songformer_isolated_v2"
LABEL_CONTRACT_VERSION = "songformer_label_contract_v2"

_MODEL_FILE_SUFFIXES = {
    ".bin",
    ".json",
    ".pt",
    ".pth",
    ".safetensors",
    ".yaml",
    ".yml",
}
_SOURCE_FILE_SUFFIXES = {".py", ".toml", ".yaml", ".yml"}


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values, axis=-1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / np.sum(exponentials, axis=-1, keepdims=True)


def _as_frame_logits(function_logits: object) -> np.ndarray:
    logits = np.asarray(function_logits, dtype=np.float64)
    if logits.ndim == 3 and logits.shape[0] == 1:
        logits = logits[0]
    if logits.ndim != 2:
        raise ValueError(
            f"function_logits must have shape [frames, classes], got {logits.shape}"
        )
    if logits.shape[0] == 0:
        raise ValueError("function_logits must contain at least one frame")
    if not np.all(np.isfinite(logits)):
        raise ValueError("function_logits contains non-finite values")
    return logits


def aggregate_segment_label_evidence(
    function_logits: object,
    *,
    segments: Sequence[Mapping[str, Any]],
    frame_rate: float,
    allowed_label_ids: Sequence[int],
    id_to_label: Mapping[int, str],
) -> list[dict[str, Any]]:
    """Aggregate frame probabilities inside final post-processed boundaries."""
    logits = _as_frame_logits(function_logits)
    label_ids = [int(label_id) for label_id in allowed_label_ids]
    if not label_ids:
        raise ValueError("allowed_label_ids must not be empty")
    if max(label_ids) >= logits.shape[1] or min(label_ids) < 0:
        raise ValueError("allowed label id is outside function_logits")
    labels = [str(id_to_label[label_id]) for label_id in label_ids]
    probabilities_by_frame = _softmax(logits[:, label_ids])
    frames = probabilities_by_frame.shape[0]
    rate = float(frame_rate)
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("frame_rate must be finite and positive")

    evidence: list[dict[str, Any]] = []
    for segment in segments:
        start = max(0.0, float(segment["start"]))
        end = max(start, float(segment["end"]))
        start_frame = min(frames, max(0, int(math.floor(start * rate))))
        end_frame = min(frames, max(start_frame, int(math.ceil(end * rate))))
        if end_frame <= start_frame:
            nearest = min(frames - 1, max(0, start_frame))
            window = probabilities_by_frame[nearest : nearest + 1]
        else:
            window = probabilities_by_frame[start_frame:end_frame]
        aggregate = window.mean(axis=0)
        aggregate = aggregate / aggregate.sum()
        probability_map = {
            label: float(value) for label, value in zip(labels, aggregate)
        }
        ranked = sorted(probability_map.values(), reverse=True)
        confidence = ranked[0]
        runner_up = ranked[1] if len(ranked) > 1 else 0.0
        evidence.append(
            {
                "label_probabilities": probability_map,
                "label_confidence": confidence,
                "label_margin": confidence - runner_up,
            }
        )
    return evidence


def attach_segment_label_evidence(
    segments: Sequence[Mapping[str, Any]],
    *,
    function_logits: object,
    frame_rate: float,
    allowed_label_ids: Sequence[int],
    id_to_label: Mapping[int, str],
) -> list[dict[str, Any]]:
    """Return segment copies with a complete probability distribution attached."""
    evidence = aggregate_segment_label_evidence(
        function_logits,
        segments=segments,
        frame_rate=frame_rate,
        allowed_label_ids=allowed_label_ids,
        id_to_label=id_to_label,
    )
    return [{**dict(segment), **item} for segment, item in zip(segments, evidence)]


def _read_hash_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"version": 1, "files": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
        return {"version": 1, "files": {}}
    return payload


def _write_hash_manifest(manifest_path: Path, payload: Mapping[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)


def sha256_file_cached(path: Path, manifest_path: Path) -> str:
    """Hash a file, reusing a digest only for the same path, size, and mtime."""
    resolved = path.expanduser().resolve()
    stat = resolved.stat()
    key = str(resolved)
    manifest = _read_hash_manifest(manifest_path)
    cached = manifest["files"].get(key)
    if (
        isinstance(cached, dict)
        and cached.get("size") == stat.st_size
        and cached.get("mtime_ns") == stat.st_mtime_ns
        and isinstance(cached.get("sha256"), str)
    ):
        return cached["sha256"]

    digest = hashlib.sha256()
    with resolved.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    manifest["files"][key] = {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": value,
    }
    _write_hash_manifest(manifest_path, manifest)
    return value


def _fingerprint_directory(
    directory: Path,
    manifest_path: Path,
    *,
    suffixes: set[str],
) -> str:
    files = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )
    if not files:
        return "empty-directory"
    digest = hashlib.sha256()
    for file_path in files:
        relative = file_path.relative_to(directory).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file_cached(file_path, manifest_path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def fingerprint_model_path(path: Path, manifest_path: Path) -> str:
    """Fingerprint one checkpoint file or a local pretrained-model directory."""
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return f"missing:{resolved}"
    if resolved.is_file():
        return sha256_file_cached(resolved, manifest_path)
    return _fingerprint_directory(
        resolved,
        manifest_path,
        suffixes=_MODEL_FILE_SUFFIXES,
    )


def source_revision(source_root: Path, manifest_path: Path) -> str:
    """Use the exact git revision or a deterministic source-tree digest."""
    resolved = source_root.expanduser().resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        revision = result.stdout.strip()
        if revision:
            return revision
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    if not resolved.exists():
        return f"missing:{resolved}"
    return "tree-sha256:" + _fingerprint_directory(
        resolved,
        manifest_path,
        suffixes=_SOURCE_FILE_SUFFIXES,
    )


def build_cache_namespace(runtime_fingerprint: Mapping[str, Any]) -> str:
    """Build a compact cache namespace from every inference-affecting input."""
    serialized = json.dumps(
        dict(runtime_fingerprint),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "songformer-" + hashlib.sha256(serialized).hexdigest()[:20]
