"""Spotify Mix EQ transition curve generation.

Implements 4 EQ transition types:
- three_band_fade: Independent low/mid/high fade
- mid_bass_swap: Mid-point bass handover
- tail_bass_swap: Late bass cut on outgoing track
- head_bass_swap: Early bass mute on incoming track
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np


def _format_curve(values: np.ndarray, duration_sec: float) -> List[Tuple[float, float]]:
    steps = len(values)
    if steps == 0:
        return []
    return [
        (i / steps * duration_sec, float(values[i]))
        for i in range(steps)
    ]


def _resolve_steps(duration_beats: int, bpm: float) -> Tuple[float, int]:
    if bpm <= 0:
        bpm = 120.0
    duration_sec = duration_beats * 60.0 / bpm
    steps = max(2, int(duration_sec * 100))  # 100 points/sec
    return duration_sec, steps


def generate_three_band_fade(
    duration_beats: int,
    bpm: float,
) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Three-band fade: low/mid/high independently fade.

    Avoids spectral overlap by independently controlling each band.
    """
    duration_sec, steps = _resolve_steps(duration_beats, bpm)
    t = np.linspace(0, 1, steps)

    deck_a_curve = np.cos(t * np.pi / 2)  # Cosine fade-out
    deck_b_curve = np.sin(t * np.pi / 2)  # Sine fade-in

    return {
        'deck_a': {
            'low': _format_curve(deck_a_curve, duration_sec),
            'mid': _format_curve(deck_a_curve, duration_sec),
            'high': _format_curve(deck_a_curve, duration_sec),
        },
        'deck_b': {
            'low': _format_curve(deck_b_curve, duration_sec),
            'mid': _format_curve(deck_b_curve, duration_sec),
            'high': _format_curve(deck_b_curve, duration_sec),
        },
    }


def generate_mid_bass_swap(
    duration_beats: int,
    bpm: float,
) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Mid bass swap: bass handover at midpoint.

    Other bands cross-fade normally; bass is swapped sharply at midpoint
    to avoid muddy double-bass.
    """
    duration_sec, steps = _resolve_steps(duration_beats, bpm)
    mid_point = steps // 2
    t = np.linspace(0, 1, steps)

    # Deck A: bass cuts at midpoint, mid/high cosine fade-out
    deck_a_low = np.ones(steps)
    deck_a_low[mid_point:] = 0.0
    deck_a_mid = np.cos(t * np.pi / 2)
    deck_a_high = np.cos(t * np.pi / 2)

    # Deck B: bass enters from midpoint, mid/high sine fade-in
    deck_b_low = np.zeros(steps)
    if steps - mid_point > 0:
        post = t[mid_point:]
        if len(post) > 0:
            normalized = (post - post[0]) / (post[-1] - post[0]) if post[-1] != post[0] else np.zeros_like(post)
            deck_b_low[mid_point:] = np.sin(normalized * np.pi / 2)
    deck_b_mid = np.sin(t * np.pi / 2)
    deck_b_high = np.sin(t * np.pi / 2)

    return {
        'deck_a': {
            'low': _format_curve(deck_a_low, duration_sec),
            'mid': _format_curve(deck_a_mid, duration_sec),
            'high': _format_curve(deck_a_high, duration_sec),
        },
        'deck_b': {
            'low': _format_curve(deck_b_low, duration_sec),
            'mid': _format_curve(deck_b_mid, duration_sec),
            'high': _format_curve(deck_b_high, duration_sec),
        },
    }


def generate_tail_bass_swap(
    duration_beats: int,
    bpm: float,
) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Tail bass swap: outgoing track bass cuts only in last 25%."""
    duration_sec, steps = _resolve_steps(duration_beats, bpm)
    tail_start = int(steps * 0.75)
    t = np.linspace(0, 1, steps)

    deck_a_low = np.ones(steps)
    if steps - tail_start > 0:
        deck_a_low[tail_start:] = np.linspace(1.0, 0.0, steps - tail_start)
    deck_a_mid = np.cos(t * np.pi / 2)
    deck_a_high = np.cos(t * np.pi / 2)

    deck_b_low = np.sin(t * np.pi / 2)
    deck_b_mid = np.sin(t * np.pi / 2)
    deck_b_high = np.sin(t * np.pi / 2)

    return {
        'deck_a': {
            'low': _format_curve(deck_a_low, duration_sec),
            'mid': _format_curve(deck_a_mid, duration_sec),
            'high': _format_curve(deck_a_high, duration_sec),
        },
        'deck_b': {
            'low': _format_curve(deck_b_low, duration_sec),
            'mid': _format_curve(deck_b_mid, duration_sec),
            'high': _format_curve(deck_b_high, duration_sec),
        },
    }


def generate_head_bass_swap(
    duration_beats: int,
    bpm: float,
) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Head bass swap: incoming track bass muted in first 25%."""
    duration_sec, steps = _resolve_steps(duration_beats, bpm)
    head_end = int(steps * 0.25)
    t = np.linspace(0, 1, steps)

    deck_a_low = np.cos(t * np.pi / 2)
    deck_a_mid = np.cos(t * np.pi / 2)
    deck_a_high = np.cos(t * np.pi / 2)

    deck_b_low = np.zeros(steps)
    if steps - head_end > 0:
        deck_b_low[head_end:] = np.linspace(0.0, 1.0, steps - head_end) * np.sin(t[head_end:] * np.pi / 2)
    deck_b_mid = np.sin(t * np.pi / 2)
    deck_b_high = np.sin(t * np.pi / 2)

    return {
        'deck_a': {
            'low': _format_curve(deck_a_low, duration_sec),
            'mid': _format_curve(deck_a_mid, duration_sec),
            'high': _format_curve(deck_a_high, duration_sec),
        },
        'deck_b': {
            'low': _format_curve(deck_b_low, duration_sec),
            'mid': _format_curve(deck_b_mid, duration_sec),
            'high': _format_curve(deck_b_high, duration_sec),
        },
    }


EQ_TRANSITION_GENERATORS = {
    'three_band_fade': generate_three_band_fade,
    'mid_bass_swap': generate_mid_bass_swap,
    'tail_bass_swap': generate_tail_bass_swap,
    'head_bass_swap': generate_head_bass_swap,
}


def generate_eq_transition(
    eq_type: str,
    duration_beats: int,
    bpm: float,
) -> Dict[str, Any]:
    """Generate EQ transition curves.

    Args:
        eq_type: three_band_fade | mid_bass_swap | tail_bass_swap | head_bass_swap
        duration_beats: Transition length in beats.
        bpm: Current BPM.

    Returns:
        {deck_a: {low, mid, high}, deck_b: {low, mid, high}}
    """
    if eq_type not in EQ_TRANSITION_GENERATORS:
        raise ValueError(
            f"Unknown EQ type: {eq_type}. "
            f"Available: {list(EQ_TRANSITION_GENERATORS.keys())}"
        )
    return EQ_TRANSITION_GENERATORS[eq_type](duration_beats, bpm)
