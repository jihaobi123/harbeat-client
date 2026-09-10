"""MDX23C drum separation and ADTOF drum transcription."""

from __future__ import annotations


def analyze_drums(drum_audio_path: str, output_dir: str, device: str = "auto"):
    """Lazy public entry point that also keeps ``python -m ...pipeline`` clean."""
    from .pipeline import analyze_drums as run

    return run(drum_audio_path, output_dir, device)


__all__ = ["analyze_drums"]
