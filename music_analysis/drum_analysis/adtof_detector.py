"""ADTOF-pytorch adapter exposing MIDI, timestamps, and activation confidence."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .mdx23c_separator import _is_cuda_oom, resolve_device
from .schemas import DRUM_CLASSES, DrumEvent, empty_events


logger = logging.getLogger(__name__)

FPS = 100
THRESHOLDS = (0.22, 0.24, 0.32, 0.22, 0.30)
MIDI_LABELS = (35, 38, 47, 42, 49)
# Upstream activation order follows MIDI_LABELS, where note 47 is tom and
# note 42 is hi-hat.  It intentionally differs from our public JSON order.
ADTOF_CLASS_NAMES = ("kick", "snare", "tom", "hihat", "cymbal")
_MODEL_CACHE: dict[tuple[str, str], Any] = {}
_MODEL_LOCK = threading.Lock()
_MODEL_INFERENCE_LOCK = threading.Lock()


class DrumTranscriptionError(RuntimeError):
    """Raised when ADTOF cannot produce drum events and MIDI."""


def _load_model(device: str, weights: str | Path | None = None) -> Any:
    try:
        from adtof_pytorch import (
            calculate_n_bins,
            create_frame_rnn_model,
            get_default_weights_path,
            load_pytorch_weights,
        )
    except ImportError as exc:
        raise DrumTranscriptionError(
            "ADTOF-pytorch is not installed; install requirements-drum-analysis.txt"
        ) from exc

    resolved_weights = Path(weights or get_default_weights_path() or "").expanduser()
    if not resolved_weights.is_file():
        raise DrumTranscriptionError(f"ADTOF weights are unavailable: {resolved_weights}")
    key = (device, str(resolved_weights.resolve()))
    with _MODEL_LOCK:
        if key in _MODEL_CACHE:
            return _MODEL_CACHE[key]
        logger.info("Loading ADTOF model once on %s", device)
        model = create_frame_rnn_model(calculate_n_bins())
        model = load_pytorch_weights(model, str(resolved_weights), strict=False)
        model.eval().to(device)
        _MODEL_CACHE[key] = model
        return model


def _infer(audio_path: Path, device: str, weights: str | Path | None) -> np.ndarray:
    import torch

    from adtof_pytorch import load_audio_for_model

    model = _load_model(device, weights)
    features = load_audio_for_model(str(audio_path)).to(device)
    with _MODEL_INFERENCE_LOCK, torch.inference_mode():
        return model(features).detach().cpu().numpy()


def _events_and_peaks(
    activations: np.ndarray,
    thresholds: Sequence[float],
    fps: int,
) -> tuple[dict[str, list[DrumEvent]], dict[int, list[float]]]:
    from adtof_pytorch import PeakPicker

    values = np.asarray(activations, dtype=np.float32)
    if values.ndim != 3 or values.shape[0] != 1 or values.shape[2] != 5:
        raise DrumTranscriptionError(f"Unexpected ADTOF activation shape: {values.shape}")
    peaks = PeakPicker(thresholds=thresholds, fps=fps).pick(
        values, labels=MIDI_LABELS, label_offset=0
    )[0]
    events = empty_events()
    for class_index, (name, midi_note) in enumerate(zip(ADTOF_CLASS_NAMES, MIDI_LABELS)):
        for time_sec in peaks.get(midi_note, []):
            frame = int(np.clip(round(float(time_sec) * fps), 0, values.shape[1] - 1))
            events[name].append(
                {
                    "time": round(float(time_sec), 3),
                    "confidence": round(float(values[0, frame, class_index]), 4),
                }
            )
    return events, peaks


class ADTOFDrumDetector:
    """Transcribe many drum files while reusing one loaded ADTOF model."""

    def __init__(
        self,
        device: str = "auto",
        *,
        fps: int = FPS,
        thresholds: Sequence[float] = THRESHOLDS,
        weights: str | Path | None = None,
    ) -> None:
        if fps != FPS:
            raise ValueError(f"The first integration is fixed at {FPS} fps")
        if len(tuple(thresholds)) != len(DRUM_CLASSES):
            raise ValueError("ADTOF requires exactly five per-class thresholds")
        self.requested_device = device
        self.device = resolve_device(device)
        self.fps = fps
        self.thresholds = tuple(float(value) for value in thresholds)
        self.weights = weights

    def transcribe(
        self, input_path: str | Path, midi_path: str | Path
    ) -> dict[str, Any]:
        source = Path(input_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Drum audio does not exist: {source}")
        destination = Path(midi_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            activations = _infer(source, self.device, self.weights)
        except Exception as exc:
            if not self.device.startswith("cuda") or not _is_cuda_oom(exc):
                if isinstance(exc, DrumTranscriptionError):
                    raise
                raise DrumTranscriptionError(f"ADTOF inference failed: {exc}") from exc
            logger.exception("ADTOF CUDA OOM; retrying the same input on CPU")
            try:
                import torch

                torch.cuda.empty_cache()
            except (ImportError, AttributeError):
                pass
            self.device = "cpu"
            activations = _infer(source, "cpu", self.weights)

        events, peaks = _events_and_peaks(activations, self.thresholds, self.fps)
        from adtof_pytorch import activations_to_pretty_midi

        midi = activations_to_pretty_midi(
            peaks, velocity=100, note_duration=0.1, program=1, is_drum=True
        )
        if destination.exists():
            destination.unlink()
        midi.write(str(destination))
        return {
            "events": events,
            "midi_path": destination,
            "device": self.device,
            "fps": self.fps,
            "thresholds": list(self.thresholds),
            "activation_frames": int(activations.shape[1]),
        }


def clear_model_cache() -> None:
    """Testing/service-shutdown hook; normal calls should keep the cache warm."""
    with _MODEL_LOCK:
        _MODEL_CACHE.clear()
