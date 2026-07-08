"""Spotify Mix filter transition curve generation.

Provides lowpass/highpass filter sweeps with exponential frequency curves
that match human pitch perception.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

# Frequency range constants (Hz)
FULL_FREQ = 22050.0
LOWPASS_MIN = 200.0
HIGHPASS_MAX = 2000.0
HIGHPASS_MIN = 20.0


def _exponential_freq_curve(start_freq: float, end_freq: float, steps: int) -> np.ndarray:
    """Exponential frequency curve (matches human pitch perception)."""
    log_start = np.log(max(start_freq, 1.0))
    log_end = np.log(max(end_freq, 1.0))
    return np.exp(np.linspace(log_start, log_end, max(steps, 2)))


def _resolve_steps(duration_beats: int, bpm: float) -> Tuple[float, int]:
    if bpm <= 0:
        bpm = 120.0
    duration_sec = duration_beats * 60.0 / bpm
    steps = max(2, int(duration_sec * 100))
    return duration_sec, steps


def _format_freq_curve(freqs: np.ndarray, duration_sec: float) -> List[Tuple[float, float]]:
    steps = len(freqs)
    return [(i / steps * duration_sec, float(freqs[i])) for i in range(steps)]


def generate_lowpass_filter_in(
    duration_beats: int,
    bpm: float,
    target_freq: float = LOWPASS_MIN,
) -> Dict[str, Any]:
    """Lowpass filter cut-in: high → target frequency, gradually removing highs."""
    duration_sec, steps = _resolve_steps(duration_beats, bpm)
    freq_curve = _exponential_freq_curve(FULL_FREQ, target_freq, steps)
    return {
        'filter_type': 'lowpass',
        'frequency': _format_freq_curve(freq_curve, duration_sec),
        'q_factor': 1.0,
    }


def generate_lowpass_filter_out(
    duration_beats: int,
    bpm: float,
    start_freq: float = LOWPASS_MIN,
) -> Dict[str, Any]:
    """Lowpass filter cut-out: target → full frequency, restoring highs."""
    duration_sec, steps = _resolve_steps(duration_beats, bpm)
    freq_curve = _exponential_freq_curve(start_freq, FULL_FREQ, steps)
    return {
        'filter_type': 'lowpass',
        'frequency': _format_freq_curve(freq_curve, duration_sec),
        'q_factor': 1.0,
    }


def generate_highpass_filter_in(
    duration_beats: int,
    bpm: float,
    target_freq: float = HIGHPASS_MAX,
) -> Dict[str, Any]:
    """Highpass filter cut-in: low → target frequency, gradually removing lows."""
    duration_sec, steps = _resolve_steps(duration_beats, bpm)
    freq_curve = _exponential_freq_curve(HIGHPASS_MIN, target_freq, steps)
    return {
        'filter_type': 'highpass',
        'frequency': _format_freq_curve(freq_curve, duration_sec),
        'q_factor': 1.0,
    }


def generate_highpass_filter_out(
    duration_beats: int,
    bpm: float,
    start_freq: float = HIGHPASS_MAX,
) -> Dict[str, Any]:
    """Highpass filter cut-out: target → low frequency, restoring lows."""
    duration_sec, steps = _resolve_steps(duration_beats, bpm)
    freq_curve = _exponential_freq_curve(start_freq, HIGHPASS_MIN, steps)
    return {
        'filter_type': 'highpass',
        'frequency': _format_freq_curve(freq_curve, duration_sec),
        'q_factor': 1.0,
    }


def generate_dj_filter_curve(
    duration_beats: int,
    bpm: float,
    knob_curve: List[float],
) -> Dict[str, Any]:
    """DJ-style single-knob filter.

    knob_curve values in [-1, 1]:
        -1: Full lowpass (200Hz)
         0: Bypass (no filter)
        +1: Full highpass (2000Hz)
    """
    duration_sec, _ = _resolve_steps(duration_beats, bpm)
    steps = len(knob_curve) or 1

    frequencies: List[float] = []
    filter_types: List[str] = []

    for value in knob_curve:
        if value < -0.05:
            freq = FULL_FREQ * np.power(LOWPASS_MIN / FULL_FREQ, -value)
            ftype = 'lowpass'
        elif value > 0.05:
            freq = HIGHPASS_MIN * np.power(HIGHPASS_MAX / HIGHPASS_MIN, value)
            ftype = 'highpass'
        else:
            freq = FULL_FREQ
            ftype = 'bypass'
        frequencies.append(float(freq))
        filter_types.append(ftype)

    return {
        'filter_type': 'dynamic',
        'frequency': [(i / steps * duration_sec, frequencies[i]) for i in range(steps)],
        'filter_types': filter_types,
        'q_factor': 1.0,
    }


FILTER_TRANSITION_GENERATORS = {
    'lowpass_in': generate_lowpass_filter_in,
    'lowpass_out': generate_lowpass_filter_out,
    'highpass_in': generate_highpass_filter_in,
    'highpass_out': generate_highpass_filter_out,
}


def generate_filter_transition(
    filter_type: str,
    duration_beats: int,
    bpm: float,
) -> Dict[str, Any]:
    """Generate filter transition curve."""
    if filter_type not in FILTER_TRANSITION_GENERATORS:
        raise ValueError(
            f"Unknown filter type: {filter_type}. "
            f"Available: {list(FILTER_TRANSITION_GENERATORS.keys())}"
        )
    return FILTER_TRANSITION_GENERATORS[filter_type](duration_beats, bpm)


def generate_combined_filter(
    deck_a_filter: str,
    deck_b_filter: str,
    duration_beats: int,
    bpm: float,
) -> Dict[str, Any]:
    """Combined filter: apply different filters to deck A and deck B simultaneously."""
    return {
        'deck_a': generate_filter_transition(deck_a_filter, duration_beats, bpm),
        'deck_b': generate_filter_transition(deck_b_filter, duration_beats, bpm),
    }
