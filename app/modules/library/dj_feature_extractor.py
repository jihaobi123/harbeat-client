"""DJ-style feature extractor — fingerprint of an audio file usable for
weighted dance-style scoring.

Computes ~25 numeric features in three layers:

  Rhythm layer  (pure: from beat_points + downbeats — no audio decode)
  Stem layer    (cheap: per-stem RMS + selective FFT bands)
  Timbre layer  (librosa MFCC / spectral centroid / rolloff / contrast)

All values are JSON-friendly Python floats. Output dict slots into
LibrarySong.music_features under the "dj" key; existing music_features
contents are preserved.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# Feature schema version — bump when changing extractor logic so consumers
# can detect stale features.
FEATURE_VERSION = 1


# How many seconds of audio to analyse for timbre features. Full-song MFCC is
# expensive; 30s slice from the middle is plenty for fingerprinting.
TIMBRE_WINDOW_SEC = 30.0


def _safe_float(value, default: float = 0.0) -> float:
    try:
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except Exception:
        return default


def _rms_soft(y: np.ndarray) -> float:
    """Return tanh-soft-clipped RMS in 0..1 range for cross-stem comparison."""
    if y is None or len(y) == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(y))))
    return _safe_float(np.tanh(rms * 4.0))


def _band_energy_ratio(y: np.ndarray, sr: int, lo: float, hi: float) -> float:
    """Fraction of magnitude-spectrum energy in [lo,hi] Hz."""
    import librosa
    if y is None or len(y) < sr:
        return 0.0
    n_fft = 2048
    S = np.abs(librosa.stft(y, n_fft=n_fft))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    mask = (freqs >= lo) & (freqs <= hi)
    band = float(S[mask].sum())
    total = float(S.sum()) or 1.0
    return _safe_float(band / total)


def _load_mono(path, sr: int = 22050,
               offset: float = 0.0, duration=None):
    import librosa
    y, sr = librosa.load(str(path), sr=sr, mono=True, offset=offset, duration=duration)
    return y, sr


# --------------------------------------------------------------------------- #
# Rhythm layer
# --------------------------------------------------------------------------- #
def rhythm_features(beat_points, downbeats, duration: float, bpm) -> dict:
    feats: dict[str, float] = {}
    feats["bpm"] = _safe_float(bpm)
    feats["duration"] = _safe_float(duration)

    if beat_points and duration > 0:
        feats["beat_density"] = _safe_float(len(beat_points) / duration)
    else:
        feats["beat_density"] = 0.0

    if beat_points and len(beat_points) >= 4:
        ibi = np.diff(np.asarray(beat_points, dtype=float))
        ibi = ibi[ibi > 0]
        if len(ibi) >= 3:
            feats["ibi_mean"] = _safe_float(ibi.mean())
            feats["ibi_std"] = _safe_float(ibi.std())
            feats["groove_complexity"] = _safe_float(ibi.std() / (ibi.mean() + 1e-6))
            odd = ibi[0::2]
            even = ibi[1::2]
            n = min(len(odd), len(even))
            if n >= 2:
                feats["swing_ratio"] = _safe_float(odd[:n].mean() / (even[:n].mean() + 1e-6))
            else:
                feats["swing_ratio"] = 1.0
        else:
            feats.update({"ibi_mean": 0.0, "ibi_std": 0.0,
                          "groove_complexity": 0.0, "swing_ratio": 1.0})
    else:
        feats.update({"ibi_mean": 0.0, "ibi_std": 0.0,
                      "groove_complexity": 0.0, "swing_ratio": 1.0})

    if downbeats and beat_points and len(beat_points) >= 8:
        ratio = len(downbeats) / len(beat_points)
        feats["four_on_floor"] = _safe_float(max(0.0, 1.0 - abs(ratio - 0.25) * 3.0))
        if len(downbeats) >= 3:
            dbi = np.diff(np.asarray(downbeats, dtype=float))
            feats["downbeat_consistency"] = _safe_float(
                1.0 - min(1.0, float(dbi.std() / (dbi.mean() + 1e-6)))
            )
        else:
            feats["downbeat_consistency"] = 0.0
    else:
        feats["four_on_floor"] = 0.0
        feats["downbeat_consistency"] = 0.0
    return feats


# --------------------------------------------------------------------------- #
# Stem layer
# --------------------------------------------------------------------------- #
STEM_KEYS = ("vocals", "drums", "bass", "other")


def stem_features(stems_paths) -> dict:
    feats: dict[str, float] = {f"{k}_rms": 0.0 for k in STEM_KEYS}
    feats.update({
        "bass_dominance": 0.0,
        "drums_to_vocals_ratio": 0.0,
        "sub_bass_score": 0.0,
        "brass_likely": 0.0,
    })
    if not stems_paths:
        return feats
    rms = {}
    sr = 22050
    bass_y = None
    other_y = None
    for k in STEM_KEYS:
        p = stems_paths.get(k)
        if not p or not os.path.isfile(p):
            continue
        try:
            y, sr = _load_mono(p, sr=sr)
            rms[k] = _rms_soft(y)
            feats[f"{k}_rms"] = rms[k]
            if k == "bass":
                bass_y = y
            elif k == "other":
                other_y = y
        except Exception:
            logger.warning("[dj-feat] stem load failed: %s", p, exc_info=True)
    total_rms = sum(rms.values()) or 1.0
    if rms.get("bass"):
        feats["bass_dominance"] = _safe_float(rms["bass"] / total_rms)
    if rms.get("vocals", 0) > 0:
        feats["drums_to_vocals_ratio"] = _safe_float(
            rms.get("drums", 0) / (rms["vocals"] + 1e-6)
        )
    if bass_y is not None:
        feats["sub_bass_score"] = _band_energy_ratio(bass_y, sr, 20, 100)
    if other_y is not None:
        feats["brass_likely"] = _band_energy_ratio(other_y, sr, 500, 3000)
    return feats


# --------------------------------------------------------------------------- #
# Timbre layer
# --------------------------------------------------------------------------- #
def timbre_features(original_path, duration: float) -> dict:
    feats = {
        "spectral_centroid": 0.0,
        "spectral_rolloff": 0.0,
        "spectral_contrast_mean": 0.0,
        "zero_crossing_rate": 0.0,
        "mfcc_mean": 0.0,
        "mfcc_std": 0.0,
        "tempogram_peak": 0.0,
    }
    if not original_path or not os.path.isfile(str(original_path)):
        return feats
    try:
        import librosa
        if duration > TIMBRE_WINDOW_SEC:
            offset = max(0.0, (duration / 2.0) - (TIMBRE_WINDOW_SEC / 2.0))
        else:
            offset = 0.0
        win = min(TIMBRE_WINDOW_SEC, max(duration, 5.0))
        y, sr = _load_mono(original_path, sr=22050, offset=offset, duration=win)
        if len(y) < sr:
            return feats
        feats["spectral_centroid"] = _safe_float(
            float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
        )
        feats["spectral_rolloff"] = _safe_float(
            float(librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85).mean())
        )
        feats["spectral_contrast_mean"] = _safe_float(
            float(librosa.feature.spectral_contrast(y=y, sr=sr).mean())
        )
        feats["zero_crossing_rate"] = _safe_float(
            float(librosa.feature.zero_crossing_rate(y).mean())
        )
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        feats["mfcc_mean"] = _safe_float(float(mfcc.mean()))
        feats["mfcc_std"] = _safe_float(float(mfcc.std()))
        try:
            tg = librosa.feature.tempogram(y=y, sr=sr)
            feats["tempogram_peak"] = _safe_float(float(tg.max()))
        except Exception:
            pass
    except Exception:
        logger.warning("[dj-feat] timbre extraction failed for %s",
                       original_path, exc_info=True)
    return feats


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def extract_dj_features(song) -> dict:
    """Build the full DJ feature dict for one LibrarySong-like object.

    The object must expose: source_path, duration, bpm, energy, beat_points,
    downbeats, stems (dict of name->path or None).
    """
    out: dict[str, Any] = {"version": FEATURE_VERSION}

    out.update(rhythm_features(
        beat_points=list(getattr(song, "beat_points", []) or []),
        downbeats=list(getattr(song, "downbeats", []) or []),
        duration=float(getattr(song, "duration", 0) or 0),
        bpm=getattr(song, "bpm", None),
    ))
    out["energy"] = _safe_float(getattr(song, "energy", None), default=0.5)
    out.update(stem_features(getattr(song, "stems", None) or None))
    out.update(timbre_features(
        original_path=getattr(song, "source_path", ""),
        duration=float(getattr(song, "duration", 0) or 0),
    ))
    return out


def update_library_song_dj_features(db, song, features: dict) -> None:
    """Merge features into LibrarySong.music_features['dj'] and commit."""
    mf = dict(getattr(song, "music_features", {}) or {})
    mf["dj"] = features
    song.music_features = mf
    db.add(song)
    db.commit()
