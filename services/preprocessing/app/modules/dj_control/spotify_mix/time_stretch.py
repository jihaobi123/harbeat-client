"""Time stretching using phase vocoder for BPM matching without pitch change.

Implements the Phase Vocoder algorithm described in Spotify Mix docs.
Uses librosa's STFT-based time stretching with phase correction.
"""
from __future__ import annotations

import numpy as np
from typing import Tuple


def phase_vocoder_stretch(
    audio: np.ndarray,
    sr: int,
    tempo_ratio: float,
    hop_length: int = 512,
) -> np.ndarray:
    """Apply phase vocoder time stretching.

    Args:
        audio: Input audio samples (mono)
        sr: Sample rate
        tempo_ratio: Speed multiplier (>1 faster, <1 slower)
        hop_length: STFT hop length

    Returns:
        Time-stretched audio with same pitch
    """
    try:
        import librosa
    except ImportError:
        raise RuntimeError("librosa required for time stretching")

    if tempo_ratio == 1.0 or tempo_ratio <= 0:
        return audio

    # librosa.effects.time_stretch uses phase vocoder internally
    return librosa.effects.time_stretch(audio, rate=tempo_ratio, hop_length=hop_length)


def compute_tempo_ratio(source_bpm: float, target_bpm: float) -> float:
    """Compute tempo ratio for BPM matching.

    Args:
        source_bpm: Original BPM
        target_bpm: Target BPM

    Returns:
        Tempo ratio (target / source)
    """
    if source_bpm <= 0:
        return 1.0
    return target_bpm / source_bpm


def time_stretch_to_bpm(
    audio: np.ndarray,
    sr: int,
    source_bpm: float,
    target_bpm: float,
    hop_length: int = 512,
) -> Tuple[np.ndarray, float]:
    """Time stretch audio to match target BPM.

    Args:
        audio: Input audio
        sr: Sample rate
        source_bpm: Original BPM
        target_bpm: Target BPM
        hop_length: STFT hop length

    Returns:
        (stretched_audio, tempo_ratio)
    """
    ratio = compute_tempo_ratio(source_bpm, target_bpm)
    stretched = phase_vocoder_stretch(audio, sr, ratio, hop_length)
    return stretched, ratio


def rubber_band_stretch(
    audio_path: str,
    output_path: str,
    tempo_ratio: float,
) -> None:
    """Alternative: use Rubber Band CLI for higher quality.

    This is a reference implementation. Requires rubberband CLI installed.

    Args:
        audio_path: Input audio file
        output_path: Output audio file
        tempo_ratio: Speed multiplier
    """
    import subprocess

    cmd = [
        "rubberband",
        "--tempo", str(tempo_ratio),
        "--pitch", "0",
        audio_path,
        output_path,
    ]
    subprocess.run(cmd, check=True)
