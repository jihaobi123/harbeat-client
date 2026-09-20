"""Optional GPU-backed vocal event detection for library analysis.

This module is intentionally non-essential: if Demucs/Torch are unavailable,
callers should catch the exception and keep the normal analysis pipeline alive.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _load_audio_with_ffmpeg(audio_path: str, *, sr: int = 44100) -> tuple["torch.Tensor", int]:
    """Decode stubborn files through ffmpeg into stereo float PCM."""
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Torch is not installed") from exc

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        audio_path,
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "2",
        "-ar",
        str(sr),
        "-",
    ]
    try:
        proc = subprocess.run(command, check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"ffmpeg failed to decode audio: {audio_path}") from exc
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size == 0:
        raise RuntimeError(f"ffmpeg decoded empty audio: {audio_path}")
    audio = audio.reshape(-1, 2).T.copy()
    return torch.from_numpy(audio), sr


def separate_stems_demucs(
    audio_path: str,
    *,
    model_name: str = "htdemucs",
    device: str | None = None,
    segment: float = 7.8,
    overlap: float = 0.25,
) -> tuple[dict[str, np.ndarray], int]:
    """Separate audio and return mono stems plus sample rate."""
    try:
        import torch
        import torchaudio
        from demucs.apply import apply_model
        from demucs.pretrained import get_model
    except ImportError as exc:
        raise RuntimeError("Demucs vocal detection dependencies are not installed") from exc

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    model = get_model(name=model_name)
    model.to(device)
    model.eval()

    try:
        wav, sr = torchaudio.load(audio_path)
    except Exception as exc:
        logger.warning("torchaudio failed for %s, falling back to ffmpeg decode: %r", audio_path, exc)
        wav, sr = _load_audio_with_ffmpeg(audio_path)
    if sr not in (44100, 48000):
        wav = torchaudio.transforms.Resample(sr, 44100)(wav)
        sr = 44100
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    elif wav.shape[0] > 2:
        wav = wav[:2]
    wav = wav.to(device)

    with torch.no_grad():
        sources = apply_model(
            model,
            wav[None],
            device=device,
            segment=segment,
            overlap=overlap,
            progress=False,
        )[0]

    stems: dict[str, np.ndarray] = {}
    for idx, name in enumerate(model.sources):
        stem = sources[idx].detach().cpu().numpy()
        if stem.ndim == 2:
            stem = stem.mean(axis=0)
        stems[str(name)] = stem.astype(np.float32, copy=False)
    return stems, int(sr)


def detect_vocal_events_from_stem(
    vocal_stem: np.ndarray,
    *,
    sr: int = 44100,
    window_sec: float = 2.0,
    hop_sec: float = 1.0,
    entry_threshold: float = 0.35,
    exit_threshold: float = 0.25,
    min_gap_sec: float = 2.0,
) -> list[dict[str, Any]]:
    """Detect vocal-active ranges from a separated vocal stem."""
    if vocal_stem.size == 0:
        return []

    window_samples = max(1, int(window_sec * sr))
    hop_samples = max(1, int(hop_sec * sr))
    if vocal_stem.shape[0] < window_samples:
        return []

    rms_values: list[float] = []
    for start in range(0, vocal_stem.shape[0] - window_samples + 1, hop_samples):
        window = vocal_stem[start : start + window_samples]
        rms_values.append(float(np.sqrt(np.mean(np.square(window))) + 1e-10))
    if not rms_values:
        return []

    rms = np.asarray(rms_values, dtype=np.float32)
    peak = float(np.max(rms))
    if peak <= 1e-9:
        return []
    relative = rms / peak

    events: list[dict[str, Any]] = []
    active = False
    event_start = 0.0
    event_peak = 0.0
    for idx, energy in enumerate(relative):
        time_sec = idx * hop_sec
        value = float(energy)
        if not active and value >= entry_threshold:
            active = True
            event_start = time_sec
            event_peak = value
            continue
        if active and value > event_peak:
            event_peak = value
            continue
        if active and value <= exit_threshold:
            if all(float(e) <= exit_threshold for e in relative[idx + 1 : idx + 3]):
                active = False
                events.append(
                    {
                        "start": round(event_start, 2),
                        "end": round(time_sec, 2),
                        "confidence": round(min(1.0, event_peak / 0.7), 3),
                    }
                )

    if active:
        events.append(
            {
                "start": round(event_start, 2),
                "end": round((len(relative) - 1) * hop_sec, 2),
                "confidence": round(min(1.0, event_peak / 0.7), 3),
            }
        )

    merged: list[dict[str, Any]] = []
    for event in events:
        if merged and float(event["start"]) - float(merged[-1]["end"]) < min_gap_sec:
            merged[-1]["end"] = event["end"]
            merged[-1]["confidence"] = max(merged[-1]["confidence"], event["confidence"])
        else:
            merged.append(event)
    return merged


def analyze_vocal_events_gpu(
    audio_path: str,
    *,
    use_gpu: bool = True,
    fast_mode: bool = False,
) -> list[dict[str, Any]]:
    """Separate vocals with Demucs and return vocal event ranges."""
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Torch is not installed") from exc

    device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
    model_name = "mdx_extra" if fast_mode else "htdemucs"
    stems, sr = separate_stems_demucs(
        audio_path,
        model_name=model_name,
        device=device,
        segment=7.8 if device == "cuda" else 4.0,
    )
    vocal = stems.get("vocals")
    if vocal is None:
        logger.warning("Demucs output did not include vocals stem for %s", audio_path)
        return []
    return detect_vocal_events_from_stem(vocal, sr=sr)


def patch_analysis_result_with_vocals(
    analysis: dict[str, Any],
    file_path: str,
    *,
    use_gpu: bool = True,
    fast_mode: bool = False,
) -> dict[str, Any]:
    """Return analysis with vocal_events filled when absent."""
    if analysis.get("vocal_events"):
        return analysis
    updated = dict(analysis)
    updated["vocal_events"] = analyze_vocal_events_gpu(
        file_path,
        use_gpu=use_gpu,
        fast_mode=fast_mode,
    )
    return updated
