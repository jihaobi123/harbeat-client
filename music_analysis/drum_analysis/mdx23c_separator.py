"""Reusable MDX23C DrumSep adapter with normalized five-stem output."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf

from .schemas import DRUM_CLASSES


logger = logging.getLogger(__name__)

MODEL_NAME = "drumsep-6stem"
TARGET_SAMPLE_RATE = 44100
_ENGINE_CACHE: dict[tuple[str, str | None], Any] = {}
_ENGINE_LOCK = threading.Lock()
_ENGINE_INFERENCE_LOCK = threading.Lock()


class DrumSeparationError(RuntimeError):
    """Raised when DrumSep cannot produce a complete, valid result."""


def resolve_device(requested: str = "auto") -> str:
    """Resolve CLI device syntax to an available Torch device."""
    import torch

    value = str(requested or "auto").strip().lower()
    if value == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if value == "cpu":
        return value
    if value == "mps":
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return value
        logger.warning("MPS was requested but is unavailable; falling back to CPU")
        return "cpu"
    if value == "cuda" or value.startswith("cuda:"):
        if ":" in value:
            try:
                index = int(value.split(":", 1)[1])
            except ValueError as exc:
                raise ValueError(f"Invalid CUDA device: {requested!r}") from exc
            if index < 0:
                raise ValueError(f"Invalid CUDA device: {requested!r}")
        if torch.cuda.is_available():
            if ":" in value:
                if index < 0 or index >= torch.cuda.device_count():
                    raise ValueError(f"CUDA device index is unavailable: {requested!r}")
            return value
        logger.warning("CUDA was requested but is unavailable; falling back to CPU")
        return "cpu"
    raise ValueError(
        f"Unsupported device {requested!r}; expected auto, cpu, cuda, cuda:N, or mps"
    )


def _is_cuda_oom(exc: BaseException) -> bool:
    try:
        import torch

        if isinstance(exc, torch.cuda.OutOfMemoryError):
            return True
    except (ImportError, AttributeError):
        pass
    message = str(exc).lower()
    return "cuda" in message and "out of memory" in message


def _load_engine(device: str, cache_dir: Path | None) -> Any:
    key = (device, str(cache_dir) if cache_dir else None)
    with _ENGINE_LOCK:
        if key in _ENGINE_CACHE:
            return _ENGINE_CACHE[key]
        try:
            from mdxnet_infer import MDX23CInference
        except ImportError as exc:
            raise DrumSeparationError(
                "mdxnet-infer is not installed; install requirements-drum-analysis.txt"
            ) from exc
        logger.info("Loading MDX23C %s once on %s", MODEL_NAME, device)
        try:
            engine = MDX23CInference.from_pretrained(
                MODEL_NAME,
                cache_dir=cache_dir,
                device=device,
                progress=False,
            )
        except Exception as exc:
            raise DrumSeparationError(
                f"Unable to download or load MDX23C {MODEL_NAME} checkpoint: {exc}"
            ) from exc
        _ENGINE_CACHE[key] = engine
        return engine


def _load_stereo_44100(path: Path) -> np.ndarray:
    try:
        audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    except Exception as exc:
        raise DrumSeparationError(f"Unable to read drum audio {path}: {exc}") from exc
    if len(audio) == 0:
        raise DrumSeparationError(f"Drum audio is empty: {path}")
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    elif audio.shape[1] > 2:
        audio = audio[:, :2]
    if sample_rate != TARGET_SAMPLE_RATE:
        audio = np.column_stack(
            [
                librosa.resample(
                    audio[:, channel], orig_sr=sample_rate, target_sr=TARGET_SAMPLE_RATE
                )
                for channel in range(2)
            ]
        )
    return np.asarray(audio, dtype=np.float32)


def _complete_audio(stem: np.ndarray, length: int) -> np.ndarray:
    value = np.asarray(stem, dtype=np.float32)
    if value.ndim == 1:
        value = np.repeat(value[:, None], 2, axis=1)
    elif value.ndim == 2 and value.shape[0] == 2 and value.shape[1] != 2:
        value = value.T
    if value.ndim != 2:
        raise DrumSeparationError(f"Unexpected MDX23C stem shape: {value.shape}")
    if value.shape[1] == 1:
        value = np.repeat(value, 2, axis=1)
    elif value.shape[1] > 2:
        value = value[:, :2]
    if len(value) < length:
        value = np.pad(value, ((0, length - len(value)), (0, 0)))
    return value[:length]


class MDX23CDrumSeparator:
    """Separate many drum files while reusing one loaded MDX23C model."""

    def __init__(self, device: str = "auto", cache_dir: str | Path | None = None) -> None:
        self.requested_device = device
        self.device = resolve_device(device)
        self.cache_dir = Path(cache_dir).expanduser().resolve() if cache_dir else None

    def _infer(self, audio: np.ndarray, device: str) -> dict[str, np.ndarray]:
        engine = _load_engine(device, self.cache_dir)
        with _ENGINE_INFERENCE_LOCK:
            return engine.separate(audio, sample_rate=TARGET_SAMPLE_RATE, progress=False)

    def separate(self, input_path: str | Path, output_dir: str | Path) -> dict[str, Path]:
        source = Path(input_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Drum audio does not exist: {source}")
        destination = Path(output_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        audio = _load_stereo_44100(source)

        try:
            raw = self._infer(audio, self.device)
        except Exception as exc:
            if not self.device.startswith("cuda") or not _is_cuda_oom(exc):
                if isinstance(exc, DrumSeparationError):
                    raise
                raise DrumSeparationError(f"MDX23C separation failed: {exc}") from exc
            logger.exception("MDX23C CUDA OOM; retrying the same input on CPU")
            try:
                import torch

                torch.cuda.empty_cache()
            except (ImportError, AttributeError):
                pass
            self.device = "cpu"
            raw = self._infer(audio, "cpu")

        expected = {"kick", "snare", "toms", "hh", "ride", "crash"}
        missing = expected.difference(raw)
        if missing:
            raise DrumSeparationError(f"MDX23C omitted required stems: {sorted(missing)}")

        # Use mdxnet-infer's own cymbal combiner as requested.
        from mdxnet_infer.utils.stems import combine_cymbal_stems

        combined = combine_cymbal_stems(dict(raw))
        normalized = {
            "kick": combined["kick"],
            "snare": combined["snare"],
            "hihat": combined["hh"],
            "tom": combined["toms"],
            "cymbal": combined["cymbals"],
        }
        paths: dict[str, Path] = {}
        for name in DRUM_CLASSES:
            output = destination / f"{name}.wav"
            sf.write(
                output,
                _complete_audio(normalized[name], len(audio)),
                TARGET_SAMPLE_RATE,
                subtype="PCM_16",
            )
            paths[name] = output
        return paths


def clear_model_cache() -> None:
    """Testing/service-shutdown hook; normal calls should keep the cache warm."""
    with _ENGINE_LOCK:
        _ENGINE_CACHE.clear()
