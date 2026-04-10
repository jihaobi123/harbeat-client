"""Diagnostic checks for GrooveEngine on Windows."""

from __future__ import annotations

import math
import time

import librosa
import numpy as np
import sounddevice as sd
import torch
from pedalboard import HighpassFilter, Pedalboard, Reverb


def _print_header(title: str) -> None:
    print("=" * 72)
    print(title)
    print("=" * 72)


def check_imports() -> None:
    """Verify critical imports succeed."""

    _print_header("1. IMPORT CHECK")
    print(f"torch version      : {torch.__version__}")
    print(f"librosa version    : {librosa.__version__}")
    print(f"sounddevice ver.   : {sd.__version__}")
    print("pedalboard import  : OK")
    print("All critical imports succeeded.")
    print()


def check_devices() -> None:
    """Print available Windows audio devices."""

    _print_header("2. AUDIO DEVICE ENUMERATION")
    devices = sd.query_devices()
    print(devices)
    print()
    try:
        print(f"Default input/output device: {sd.default.device}")
    except Exception as exc:  # pragma: no cover - diagnostics only
        print(f"Could not query default device: {exc}")
    print()


def check_pedalboard_processing(sample_rate: int = 44100) -> None:
    """Process dummy noise through a pedalboard chain."""

    _print_header("3. PEDALBOARD FX CHECK")
    rng = np.random.default_rng(42)
    noise = rng.normal(0.0, 0.05, size=(sample_rate, 2)).astype(np.float32)
    board = Pedalboard([
        Reverb(room_size=0.35, wet_level=0.2),
        HighpassFilter(cutoff_frequency_hz=180.0),
    ])
    processed = board(noise.T, sample_rate).T
    print(f"Input shape        : {noise.shape}")
    print(f"Output shape       : {processed.shape}")
    print(f"Peak amplitude     : {float(np.max(np.abs(processed))):.6f}")
    print("Pedalboard processing completed without exception.")
    print()


def check_audio_playback(sample_rate: int = 44100) -> None:
    """Play a short 440 Hz sine beep through the default output device."""

    _print_header("4. DEFAULT OUTPUT PLAYBACK CHECK")
    duration_seconds = 1.0
    frequency_hz = 440.0
    time_axis = np.arange(int(sample_rate * duration_seconds), dtype=np.float32) / sample_rate
    beep = 0.15 * np.sin(2.0 * math.pi * frequency_hz * time_axis)
    stereo_beep = np.column_stack([beep, beep]).astype(np.float32)

    print("Playing a 1-second 440 Hz test tone now...")
    sd.play(stereo_beep, samplerate=sample_rate, blocking=True)
    sd.wait()
    time.sleep(0.1)
    print("Playback call completed.")
    print("If you heard the beep, your default audio output is working.")
    print()


def main() -> int:
    """Run all environment diagnostics."""

    try:
        check_imports()
        check_devices()
        check_pedalboard_processing()
        check_audio_playback()
    except Exception as exc:
        _print_header("ENVIRONMENT CHECK FAILED")
        print(f"Error: {exc}")
        return 1

    _print_header("ENVIRONMENT CHECK PASSED")
    print("GrooveEngine core Python/audio dependencies appear operational.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
