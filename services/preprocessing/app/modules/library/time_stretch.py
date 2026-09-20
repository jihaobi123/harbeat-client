"""Library-facing time stretching helpers for offline BPM variants."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

import numpy as np

from app.modules.dj_control.spotify_mix.time_stretch import (
    compute_tempo_ratio,
    phase_vocoder_stretch,
    time_stretch_to_bpm,
)


def time_stretch_song(
    audio: np.ndarray,
    sr: int,
    source_bpm: float,
    target_bpm: float,
) -> Tuple[np.ndarray, float]:
    """Stretch a song to a target BPM without changing pitch."""
    return time_stretch_to_bpm(audio, sr, source_bpm, target_bpm)


def batch_generate_bpm_variants(
    song_id: str,
    audio_path: str,
    source_bpm: float,
    bpm_ratios: Iterable[float] = (0.85, 0.9, 0.95, 1.05, 1.1, 1.15),
    output_root: str | None = None,
) -> list[dict[str, object]]:
    """Generate offline stretched WAV variants for a song.

    The output defaults to ``<audio_dir>/<song_id>/stretched`` to match the
    implementation manual's storage convention.
    """
    import librosa
    import soundfile as sf

    source = Path(audio_path)
    if output_root is None:
        out_dir = source.parent / song_id / "stretched"
    else:
        out_dir = Path(output_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    audio, sr = librosa.load(str(source), sr=None, mono=True)
    variants: list[dict[str, object]] = []
    for ratio in bpm_ratios:
        safe_ratio = max(0.5, min(2.0, float(ratio)))
        target_bpm = float(source_bpm) * safe_ratio
        stretched, applied_ratio = time_stretch_song(audio, int(sr), source_bpm, target_bpm)
        out_path = out_dir / f"{song_id}_{target_bpm:.2f}bpm.wav"
        sf.write(str(out_path), stretched, int(sr))
        variants.append({
            "song_id": song_id,
            "path": str(out_path),
            "source_bpm": float(source_bpm),
            "target_bpm": round(target_bpm, 3),
            "tempo_ratio": round(float(applied_ratio), 6),
        })
    return variants


__all__ = [
    "batch_generate_bpm_variants",
    "compute_tempo_ratio",
    "phase_vocoder_stretch",
    "time_stretch_song",
    "time_stretch_to_bpm",
]
