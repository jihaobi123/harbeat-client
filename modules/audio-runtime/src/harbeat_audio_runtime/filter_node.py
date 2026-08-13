"""Reusable filter node for Spotify Mix transitions on RK audio-engine."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Iterable, Sequence

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from .dsp import Biquad  # noqa: E402


class FilterNode:
    """Apply static or block-wise lowpass/highpass filters."""

    def __init__(self) -> None:
        self._biquad = Biquad()

    def apply_lowpass(self, audio: np.ndarray, sr: int, cutoff_hz: float, q: float = 0.707) -> np.ndarray:
        """Apply a lowpass filter to mono or stereo audio."""
        return self._apply(audio, sr, cutoff_hz, q, highpass=False)

    def apply_highpass(self, audio: np.ndarray, sr: int, cutoff_hz: float, q: float = 0.707) -> np.ndarray:
        """Apply a highpass filter to mono or stereo audio."""
        return self._apply(audio, sr, cutoff_hz, q, highpass=True)

    def apply_dynamic_filter(
        self,
        audio: np.ndarray,
        sr: int,
        freq_curve: Sequence[tuple[float, float]] | Sequence[list[float]],
        filter_type: str = "lowpass",
        q: float = 0.707,
    ) -> np.ndarray:
        """Apply a cutoff envelope by filtering consecutive audio blocks."""
        data, was_mono = _as_stereo(audio)
        if data.size == 0 or not freq_curve:
            return audio

        out = np.empty_like(data, dtype=np.float32)
        total = data.shape[0]
        points = sorted((max(0.0, float(t)), float(freq)) for t, freq in freq_curve)
        sample_points = [(min(total, int(t * sr)), freq) for t, freq in points]
        if sample_points[0][0] > 0:
            sample_points.insert(0, (0, sample_points[0][1]))
        if sample_points[-1][0] < total:
            sample_points.append((total, sample_points[-1][1]))

        for idx, (start, freq) in enumerate(sample_points[:-1]):
            end = sample_points[idx + 1][0]
            if end <= start:
                continue
            block = data[start:end]
            if filter_type == "highpass":
                out[start:end] = self.apply_highpass(block, sr, freq, q)
            elif filter_type == "lowpass":
                out[start:end] = self.apply_lowpass(block, sr, freq, q)
            else:
                out[start:end] = block
        return out[:, 0] if was_mono else out

    def _apply(self, audio: np.ndarray, sr: int, cutoff_hz: float, q: float, *, highpass: bool) -> np.ndarray:
        data, was_mono = _as_stereo(audio)
        if data.size == 0:
            return audio
        self._biquad.reset()
        if highpass:
            self._biquad.set_hpf(float(sr), cutoff_hz, q=q)
        else:
            self._biquad.set_lpf(float(sr), cutoff_hz, q=q)
        filtered = self._biquad.process(data.astype(np.float32, copy=False)).copy()
        return filtered[:, 0] if was_mono else filtered


def _as_stereo(audio: np.ndarray) -> tuple[np.ndarray, bool]:
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 1:
        return np.column_stack([data, data]).astype(np.float32, copy=False), True
    if data.ndim == 2 and data.shape[1] == 2:
        return data.astype(np.float32, copy=False), False
    raise ValueError("audio must be mono shape (N,) or stereo shape (N, 2)")


def apply_filter_plan(audio: np.ndarray, sr: int, plan: dict) -> np.ndarray:
    """Apply a Spotify Mix filter plan dict to audio."""
    node = FilterNode()
    filter_type = str(plan.get("filter_type") or plan.get("type") or "lowpass")
    curve = plan.get("frequency") or plan.get("cutoff_hz")
    if isinstance(curve, Iterable) and not isinstance(curve, (str, bytes)):
        return node.apply_dynamic_filter(audio, sr, list(curve), filter_type=filter_type)
    cutoff = float(plan.get("cutoff_hz") or plan.get("frequency_hz") or 1000.0)
    if filter_type == "highpass":
        return node.apply_highpass(audio, sr, cutoff)
    return node.apply_lowpass(audio, sr, cutoff)
