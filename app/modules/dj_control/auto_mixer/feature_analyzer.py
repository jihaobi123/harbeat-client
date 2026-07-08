"""Feature extraction for automatic DJ mixer strategy selection."""

from __future__ import annotations

import os
from typing import Any

from app.modules.dj_control.band_analysis import clamp01


class FeatureAnalyzer:
    """Extract the small feature set used by the 5-strategy mixer package."""

    @staticmethod
    def extract_features(
        song_path_or_data: str | os.PathLike[str] | dict[str, Any] | Any,
        song_data: dict[str, Any] | Any | None = None,
    ) -> dict[str, float]:
        """Return BPM, normalized energy, and real MP3 low/mid/high ratios."""
        song_path: str | None = None
        if isinstance(song_path_or_data, (str, os.PathLike)):
            song_path = os.fspath(song_path_or_data)
            data = song_data or {}
        else:
            data = song_path_or_data
            candidate_path = _first_text(
                _get_value(data, "source_path"),
                _get_value(data, "audio_path"),
                _get_value(data, "file_path"),
                _get_value(data, "path"),
            )
            if candidate_path:
                song_path = candidate_path

        get = _getter(data)
        bpm = _float(get("bpm"), 120.0)
        energy = _normalize_energy(get("energy"), 0.5)

        if song_path:
            low, mid, high = _analyze_frequency_from_mp3(song_path)
        else:
            low, mid, high = _cached_or_default_ratios(data)

        return {
            "bpm": bpm,
            "energy": energy,
            "low_ratio": low,
            "mid_ratio": mid,
            "high_ratio": high,
        }

    @staticmethod
    def analyze(audio_path: str, duration: int = 60) -> dict[str, float]:
        """Analyze one MP3/audio file using the standalone package logic."""
        try:
            import librosa
        except Exception as exc:  # pragma: no cover - depends on runtime image
            raise RuntimeError("librosa is required for MP3 feature analysis") from exc

        y, sr = librosa.load(audio_path, sr=22050, duration=duration)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo[0]) if hasattr(tempo, "__iter__") else float(tempo)
        rms = librosa.feature.rms(y=y)[0]
        energy = float(rms.mean()) if len(rms) else 0.5
        low, mid, high = _analyze_frequency_from_mp3(audio_path, duration=duration)
        return {
            "bpm": bpm,
            "energy": _normalize_energy(energy, 0.5),
            "low_ratio": low,
            "mid_ratio": mid,
            "high_ratio": high,
        }


def get_song_file_path(song_id: str, song_data: dict[str, Any] | Any | None = None) -> str:
    """Get the local MP3/original file path for a library song."""
    for value in (
        _get_value(song_data, "source_path"),
        _get_value(song_data, "audio_path"),
        _get_value(song_data, "file_path"),
        _get_value(song_data, "path"),
    ):
        path = _first_text(value)
        if path and os.path.isfile(path):
            return path

    base_path = os.environ.get("HARBEAT_SONGS_PATH") or "/home/mark/harbeat/media/songs"
    for ext in ("mp3", "wav", "flac", "m4a", "ogg", "opus", "aac"):
        candidate = os.path.join(base_path, str(song_id), f"original.{ext}")
        if os.path.isfile(candidate):
            return candidate

    raise FileNotFoundError(f"song file not found for {song_id}")


def _analyze_frequency_from_mp3(audio_path: str, duration: int = 60) -> tuple[float, float, float]:
    """Calculate low/mid/high ratios from the real MP3/audio spectrum."""
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(audio_path)
    try:
        import librosa
        import numpy as np
    except Exception as exc:  # pragma: no cover - depends on runtime image
        raise RuntimeError("librosa and numpy are required for MP3 frequency analysis") from exc

    y, sr = librosa.load(audio_path, sr=22050, duration=duration)
    if len(y) == 0:
        return 0.35, 0.40, 0.25

    spec = np.abs(librosa.stft(y, n_fft=2048))
    nyquist = sr / 2
    low_idx = int(250 / nyquist * spec.shape[0])
    mid_idx = int(4000 / nyquist * spec.shape[0])

    low_energy = np.mean(np.sum(spec[:low_idx, :], axis=0))
    mid_energy = np.mean(np.sum(spec[low_idx:mid_idx, :], axis=0))
    high_energy = np.mean(np.sum(spec[mid_idx:, :], axis=0))

    total = float(low_energy + mid_energy + high_energy)
    if total <= 0:
        return 0.35, 0.40, 0.25
    return (
        float(low_energy / total),
        float(mid_energy / total),
        float(high_energy / total),
    )


def _cached_or_default_ratios(song_data: dict[str, Any] | Any) -> tuple[float, float, float]:
    """Use precomputed MP3 band ratios only; do not estimate from phrase/stems."""
    get = _getter(song_data)
    music_features = get("music_features")
    dj = _nested(music_features, "dj")
    low = _first_number(get("low_ratio"), _nested(dj, "low_ratio"), _nested(music_features, "low_ratio"))
    mid = _first_number(get("mid_ratio"), _nested(dj, "mid_ratio"), _nested(music_features, "mid_ratio"))
    high = _first_number(get("high_ratio"), _nested(dj, "high_ratio"), _nested(music_features, "high_ratio"))
    if low is None or mid is None or high is None:
        return 0.35, 0.40, 0.25
    return _normalize_ratios(low, mid, high)


def _get_value(song_data: dict[str, Any] | Any | None, key: str) -> Any:
    if song_data is None:
        return None
    if isinstance(song_data, dict):
        return song_data.get(key)
    return getattr(song_data, key, None)


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = os.fspath(value).strip() if isinstance(value, os.PathLike) else str(value).strip()
        if text:
            return text
    return None


def _getter(song_data: dict[str, Any] | Any):
    def get(key: str, default: Any = None) -> Any:
        if isinstance(song_data, dict):
            return song_data.get(key, default)
        return getattr(song_data, key, default)

    return get


def _nested(raw: Any, key: str) -> Any:
    return raw.get(key) if isinstance(raw, dict) else None


def _first_number(*values: Any) -> float | None:
    for value in values:
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _normalize_energy(value: Any, default: float) -> float:
    energy = _float(value, default)
    if energy > 1.0:
        energy /= 100.0
    return clamp01(energy, default)


def _normalize_ratios(low: float, mid: float, high: float) -> tuple[float, float, float]:
    low = clamp01(low, 0.35)
    mid = clamp01(mid, 0.40)
    high = clamp01(high, 0.25)
    total = low + mid + high
    if total <= 0:
        return 0.35, 0.40, 0.25
    return low / total, mid / total, high / total


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
