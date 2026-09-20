"""Frozen pure functions from the existing HarBeat backend. Do not silently change measurement definitions."""

from __future__ import annotations

import os, logging

import numpy as np

logger=logging.getLogger(__name__)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

MAJOR_TEMPLATE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])

MINOR_TEMPLATE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NOTE_MODE_TO_CAMELOT = {
    ("C", "major"): "8B", ("C#", "major"): "3B", ("D", "major"): "10B",
    ("D#", "major"): "5B", ("E", "major"): "12B", ("F", "major"): "7B",
    ("F#", "major"): "2B", ("G", "major"): "9B", ("G#", "major"): "4B",
    ("A", "major"): "11B", ("A#", "major"): "6B", ("B", "major"): "1B",
    ("C", "minor"): "5A", ("C#", "minor"): "12A", ("D", "minor"): "7A",
    ("D#", "minor"): "2A", ("E", "minor"): "9A", ("F", "minor"): "4A",
    ("F#", "minor"): "11A", ("G", "minor"): "6A", ("G#", "minor"): "1A",
    ("A", "minor"): "8A", ("A#", "minor"): "3A", ("B", "minor"): "10A",
}

def _analyze_key(y: np.ndarray, sr: int) -> dict:
    """Comprehensive key detection with cross-validation, candidates, and tonal clarity.

    Uses two chroma representations (CQT + CENS) with Krumhansl-Schmuckler template
    matching, then cross-validates to produce a confidence-weighted result.

    Returns:
        key, camelot_key, key_confidence, candidates (top 3), tonal_clarity,
        relative_ambiguity, method
    """
    import librosa

    if len(y) < sr:
        return {
            "key": "C major", "camelot_key": "8B",
            "key_confidence": 0.0, "tonal_clarity": 0.0,
            "relative_ambiguity": False, "candidates": [],
            "method": "fallback_short_audio",
        }

    # ── 1. CQT Chroma (standard, wide-band) ──────────────────────────
    try:
        chroma_cqt = librosa.feature.chroma_cqt(y=y, sr=sr, bins_per_octave=24)
        cqt_profile = np.mean(chroma_cqt, axis=1)
        if len(cqt_profile) == 12:
            chroma_12 = np.asarray(cqt_profile, dtype=float)
        elif len(cqt_profile) >= 24:
            chroma_12 = np.asarray(cqt_profile[:12] + cqt_profile[12:24], dtype=float)
        else:
            chroma_12 = np.zeros(12, dtype=float)
    except Exception:
        chroma_12 = np.zeros(12, dtype=float)

    # ── 2. CENS Chroma (noise-robust, timbre-invariant) ──────────────
    try:
        chroma_cens = librosa.feature.chroma_cens(y=y, sr=sr)
        cens_profile = np.mean(chroma_cens, axis=1)
    except Exception:
        cens_profile = np.zeros(12, dtype=float)

    # ── 3. Tonal clarity: how "peaky" is the chroma distribution ─────
    def _tonal_clarity(profile: np.ndarray) -> float:
        if np.sum(profile) <= 1e-9:
            return 0.0
        p = profile / (np.sum(profile) + 1e-9)
        # Entropy-based: low entropy = clear tonality (one note dominates)
        entropy = -np.sum(p * np.log(p + 1e-9)) / np.log(12)
        return float(np.clip(1.0 - entropy, 0.0, 1.0))

    cqt_clarity = _tonal_clarity(chroma_12)
    cens_clarity = _tonal_clarity(cens_profile)
    tonal_clarity = round(float(np.clip(cqt_clarity * 0.6 + cens_clarity * 0.4, 0.0, 1.0)), 4)

    # ── 4. K-S template matching on both chromas ─────────────────────
    def _match_templates(profile: np.ndarray) -> list[dict]:
        if np.sum(profile) <= 1e-9:
            return [{"root": "C", "mode": "major", "camelot": "8B", "score": 0.0}]
        prof = profile / (np.linalg.norm(profile) + 1e-9)
        results = []
        for idx, note in enumerate(NOTE_NAMES):
            for template, m in [(MAJOR_TEMPLATE, "major"), (MINOR_TEMPLATE, "minor")]:
                rotated = np.roll(template, idx)
                rotated = rotated / (np.linalg.norm(rotated) + 1e-9)
                score = float(np.dot(prof, rotated))
                results.append({
                    "root": note, "mode": m,
                    "camelot": NOTE_MODE_TO_CAMELOT[(note, m)],
                    "score": round(max(0.0, min(1.0, score)), 4),
                })
        results.sort(key=lambda r: -r["score"])
        return results

    cqt_results = _match_templates(chroma_12)
    cens_results = _match_templates(cens_profile)

    # ── 5. Cross-validate: weighted consensus ────────────────────────
    key_scores: dict[tuple[str, str], float] = {}  # (root, mode) → weighted score
    for i, r in enumerate(cqt_results):
        w = 0.6 * (1.0 / (i + 1))  # rank-weighted, CQT weight 0.6
        k = (r["root"], r["mode"])
        key_scores[k] = key_scores.get(k, 0.0) + w * r["score"]
    for i, r in enumerate(cens_results):
        w = 0.4 * (1.0 / (i + 1))  # rank-weighted, CENS weight 0.4
        k = (r["root"], r["mode"])
        key_scores[k] = key_scores.get(k, 0.0) + w * r["score"]

    ranked = sorted(key_scores.items(), key=lambda kv: -kv[1])
    if not ranked:
        return {
            "key": "C major", "camelot_key": "8B",
            "key_confidence": 0.0, "tonal_clarity": 0.0,
            "relative_ambiguity": False, "candidates": [],
            "method": "fallback_no_match",
        }

    # ── 6. Build candidates with cross-validated scores ──────────────
    max_score = ranked[0][1] if ranked else 1.0
    candidates = []
    for (root, mode), score in ranked[:6]:
        candidates.append({
            "root": root, "mode": mode,
            "camelot": NOTE_MODE_TO_CAMELOT[(root, mode)],
            "score": round(score / (max_score + 1e-9), 4),
        })

    best = candidates[0]
    key_confidence = round(float(np.clip(best["score"] * 0.7 + tonal_clarity * 0.3, 0.0, 1.0)), 4)

    # ── 7. Relative ambiguity detection ──────────────────────────────
    # Check if the relative major/minor is a close second
    # e.g., C major ↔ A minor (same notes, different tonal center)
    relative_ambiguity = False
    if len(candidates) >= 2:
        best_key = (best["root"], best["mode"])
        for c in candidates[1:4]:
            other_key = (c["root"], c["mode"])
            # Same set of notes = relative major/minor
            best_idx = NOTE_NAMES.index(best["root"])
            other_idx = NOTE_NAMES.index(c["root"])
            semitone_diff = (other_idx - best_idx) % 12
            # Relative minor is 3 semitones down from major (or 9 up)
            # Relative major is 3 semitones up from minor (or 9 down)
            is_relative = (best["mode"] == "major" and c["mode"] == "minor" and semitone_diff == 9) or \
                          (best["mode"] == "minor" and c["mode"] == "major" and semitone_diff == 3)
            if is_relative and c["score"] > 0.7:
                relative_ambiguity = True
                break

    # ── 8. Determine method ──────────────────────────────────────────
    cqt_best = cqt_results[0] if cqt_results else None
    cens_best = cens_results[0] if cens_results else None
    if cqt_best and cens_best and \
       cqt_best["root"] == cens_best["root"] and cqt_best["mode"] == cens_best["mode"]:
        method = "ks_cqt_cens_agree"
    else:
        method = "ks_cqt_cens_weighted"

    return {
        "key": f"{best['root']} {best['mode']}",
        "camelot_key": best["camelot"],
        "key_confidence": key_confidence,
        "tonal_clarity": tonal_clarity,
        "relative_ambiguity": relative_ambiguity,
        "candidates": candidates[:3],
        "method": method,
    }

def _build_energy_curve(
    y: np.ndarray,
    sr: int,
    *,
    window_sec: float = 2.0,
    hop_sec: float = 1.0,
) -> list[dict]:
    """Build a compact loudness contour for energy-aware phrase selection."""
    if sr <= 0 or len(y) == 0:
        return []

    mono = np.asarray(y, dtype=float)
    if mono.ndim > 1:
        mono = np.mean(mono, axis=0)
    frame_length = max(1, int(sr * window_sec))
    hop_length = max(1, int(sr * hop_sec))
    if len(mono) < frame_length:
        frame_length = len(mono)

    rms_values: list[tuple[int, int, float]] = []
    for start in range(0, max(len(mono) - frame_length + 1, 1), hop_length):
        end = min(start + frame_length, len(mono))
        chunk = mono[start:end]
        rms = float(np.sqrt(np.mean(np.square(chunk)))) if len(chunk) else 0.0
        rms_values.append((start, end, rms))

    if not rms_values:
        return []
    peak_rms = max(item[2] for item in rms_values) or 1.0
    return [{
        "start": round(start / sr, 3),
        "end": round(end / sr, 3),
        "energy": round(float(np.clip(np.tanh(rms * 8.0), 0.0, 1.0)), 4),
        "relative_energy": round(float(np.clip(rms / peak_rms, 0.0, 1.0)), 4),
    } for start, end, rms in rms_values]

def _analyze_loudness(
    y: np.ndarray,
    sr: int,
    *,
    target_lufs: float = -14.0,
    peak_headroom_db: float = 1.0,
) -> dict:
    """Measure playback loudness and derive a conservative replay gain."""
    audio = np.asarray(y, dtype=float)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=0)
    audio = audio.reshape(-1)

    if sr <= 0 or len(audio) == 0:
        audio = np.zeros(1, dtype=float)

    abs_audio = np.abs(audio)
    peak = float(np.max(abs_audio))
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if peak <= 1e-9 or rms <= 1e-9:
        return {
            "integrated_lufs": None,
            "loudness_method": "silence",
            "peak_dbfs": None,
            "rms_dbfs": None,
            "crest_factor_db": 0.0,
            "clip_ratio": 0.0,
            "replay_gain_db": 0.0,
            "clipping_risk": False,
        }

    peak_dbfs = 20.0 * np.log10(peak)
    rms_dbfs = 20.0 * np.log10(rms)
    loudness_method = "rms_dbfs_fallback"
    integrated_lufs = rms_dbfs
    try:
        import pyloudnorm as pyln

        measured = float(pyln.Meter(sr).integrated_loudness(audio))
        if np.isfinite(measured):
            integrated_lufs = measured
            loudness_method = "ebu_r128"
    except Exception:
        pass

    clip_ratio = float(np.mean(abs_audio >= 0.999))
    target_gain = float(target_lufs - integrated_lufs)
    max_gain_with_headroom = float(-peak_headroom_db - peak_dbfs)
    replay_gain = min(target_gain, max_gain_with_headroom)
    replay_gain = float(np.clip(replay_gain, -12.0, 12.0))
    clipping_risk = clip_ratio > 0.00001 or peak_dbfs >= -0.1

    return {
        "integrated_lufs": round(float(integrated_lufs), 3),
        "loudness_method": loudness_method,
        "peak_dbfs": round(float(peak_dbfs), 3),
        "rms_dbfs": round(float(rms_dbfs), 3),
        "crest_factor_db": round(float(peak_dbfs - rms_dbfs), 3),
        "clip_ratio": round(clip_ratio, 6),
        "replay_gain_db": round(replay_gain, 3),
        "clipping_risk": bool(clipping_risk),
    }

TIMBRE_WINDOW_SEC = 30.0

def _safe_float(value, default: float = 0.0) -> float:
    try:
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except Exception:
        return default

def _load_mono(path, sr: int = 22050,
               offset: float = 0.0, duration=None):
    import librosa
    y, sr = librosa.load(str(path), sr=sr, mono=True, offset=offset, duration=duration)
    return y, sr

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

SOURCE_HASHES = {'app/modules/library/analysis.py': 'b05dadffd904660ff0e8e7a4d8dc832933e005b5e22eaaa5481cf79800efea17', 'app/modules/library/dj_feature_extractor.py': '8a09dcd31aa064e0699608d7540b6cbb632df72d5529403da6bd9c21000da367'}
