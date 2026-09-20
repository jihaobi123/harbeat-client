"""Spotify Mix volume curve library.

Provides a unified library of volume fade curves for transitions:
- equal_power_sine: cosine/sine equal-power crossfade (default)
- linear: simple linear fade
- exponential: exponential curves (slower start/end)
- smooth: S-curve (sigmoid)
- overlap: partial overlap (no fade)
- quick_out: fast tail fadeout, slow head fadein
- instant: immediate switch (cut)
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np


def equal_power_sine(steps: int) -> Tuple[np.ndarray, np.ndarray]:
    """Equal-power sine/cosine crossfade (default Spotify Mix curve).

    fade_out² + fade_in² = 1 → no dip in perceived loudness for uncorrelated signals.
    """
    steps = max(2, steps)
    t = np.linspace(0, 1, steps)
    fade_out = np.cos(t * np.pi / 2)
    fade_in = np.sin(t * np.pi / 2)
    return fade_out, fade_in


def linear_fade(steps: int) -> Tuple[np.ndarray, np.ndarray]:
    """Linear fade.

    Note: causes -6dB perceived dip at midpoint for uncorrelated signals.
    Use only when correlated content is expected (e.g., same DJ-edit).
    """
    steps = max(2, steps)
    t = np.linspace(0, 1, steps)
    return 1.0 - t, t


def exponential_fade(steps: int, k: float = 3.0) -> Tuple[np.ndarray, np.ndarray]:
    """Exponential fade.

    Slower at boundaries, faster in middle. k controls steepness.
    """
    steps = max(2, steps)
    t = np.linspace(0, 1, steps)
    fade_out = np.exp(-k * t)
    fade_in = 1.0 - np.exp(-k * (1.0 - t))
    # Normalize so endpoints hit 0 and 1 exactly
    fade_out = (fade_out - fade_out[-1]) / (fade_out[0] - fade_out[-1])
    fade_in = (fade_in - fade_in[0]) / (fade_in[-1] - fade_in[0])
    return fade_out, fade_in


def smooth_fade(steps: int, k: float = 6.0) -> Tuple[np.ndarray, np.ndarray]:
    """S-curve (sigmoid) fade.

    Smooth at endpoints, steep in middle. Good for energy-up transitions.
    """
    steps = max(2, steps)
    t = np.linspace(0, 1, steps)
    sigmoid = 1.0 / (1.0 + np.exp(-k * (t - 0.5)))
    # Normalize to [0,1]
    sigmoid = (sigmoid - sigmoid[0]) / (sigmoid[-1] - sigmoid[0])
    fade_in = sigmoid
    fade_out = 1.0 - sigmoid
    return fade_out, fade_in


def overlap_fade(steps: int, overlap_pct: float = 0.5) -> Tuple[np.ndarray, np.ndarray]:
    """Partial overlap (no fade in overlap region).

    Args:
        overlap_pct: 0.0-1.0, fraction of duration where both tracks play at full volume.
    """
    steps = max(2, steps)
    overlap_pct = max(0.0, min(1.0, overlap_pct))
    edge_steps = max(1, int(steps * (1.0 - overlap_pct) / 2))

    fade_out = np.ones(steps)
    fade_in = np.ones(steps)
    if edge_steps > 0:
        fade_in[:edge_steps] = np.linspace(0, 1, edge_steps)
        fade_out[-edge_steps:] = np.linspace(1, 0, edge_steps)
    return fade_out, fade_in


def quick_out(steps: int) -> Tuple[np.ndarray, np.ndarray]:
    """Fast tail fadeout, slow head fadein.

    Outgoing track exits in first 30%, incoming fades in over full duration.
    """
    steps = max(2, steps)
    t = np.linspace(0, 1, steps)
    out_end = max(1, int(steps * 0.3))
    fade_out = np.ones(steps)
    fade_out[:out_end] = np.linspace(1, 0, out_end)
    fade_out[out_end:] = 0
    fade_in = np.sin(t * np.pi / 2)
    return fade_out, fade_in


def instant(steps: int) -> Tuple[np.ndarray, np.ndarray]:
    """Instant switch (cut). All-or-nothing at midpoint."""
    steps = max(2, steps)
    mid = steps // 2
    fade_out = np.ones(steps)
    fade_out[mid:] = 0
    fade_in = np.zeros(steps)
    fade_in[mid:] = 1
    return fade_out, fade_in


VOLUME_CURVE_GENERATORS = {
    'equal_power_sine': equal_power_sine,
    'linear': linear_fade,
    'exponential_in': exponential_fade,
    'exponential': exponential_fade,
    'smooth': smooth_fade,
    'overlap': overlap_fade,
    'quick_out': quick_out,
    'instant': instant,
}


def generate_volume_curve(
    curve_type: str,
    duration_beats: int,
    bpm: float,
) -> dict:
    """Generate volume curve for both decks.

    Args:
        curve_type: One of VOLUME_CURVE_GENERATORS keys.
        duration_beats: Duration in beats.
        bpm: Current BPM.

    Returns:
        {'deck_a': [(t, v), ...], 'deck_b': [(t, v), ...]}
    """
    if curve_type not in VOLUME_CURVE_GENERATORS:
        raise ValueError(
            f"Unknown volume curve: {curve_type}. "
            f"Available: {list(VOLUME_CURVE_GENERATORS.keys())}"
        )

    if bpm <= 0:
        bpm = 120.0
    duration_sec = duration_beats * 60.0 / bpm
    steps = max(2, int(duration_sec * 100))

    fade_out, fade_in = VOLUME_CURVE_GENERATORS[curve_type](steps)

    return {
        'deck_a': [(i / steps * duration_sec, float(fade_out[i])) for i in range(steps)],
        'deck_b': [(i / steps * duration_sec, float(fade_in[i])) for i in range(steps)],
        'duration_sec': duration_sec,
        'curve_type': curve_type,
    }
