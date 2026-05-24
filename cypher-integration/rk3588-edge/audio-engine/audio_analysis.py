"""
Audio Analysis: BPM detection, beat grid tracking, downbeat detection,
phrase structure analysis, and energy profiling.

Runs on raw audio (mono, any sample rate). No stems required.
Core dependency: numpy + scipy (already in engine requirements).

The pipeline:
  1. Onset strength envelope → autocorrelation → BPM + confidence
  2. Dynamic-programming beat tracker locked to detected BPM
  3. Downbeat detection via low-frequency energy pattern matching
  4. Phrase boundary detection via spectral novelty + bar-grid snapping
  5. Energy curve (RMS) for loudness profile

All algorithms are optimised for RK3588 — O(N) or O(N log N) where
possible, no deep learning, no external models.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal as scipy_signal
from scipy import ndimage

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

BPM_MIN, BPM_MAX = 60.0, 200.0       # Valid BPM search range
ONSET_WINDOW_S = 0.008               # 8ms onset detection window
ONSET_SMOOTH_HZ = 12.0               # Lowpass cutoff for onset envelope
N_FFT = 2048
HOP_LENGTH = 512
BASS_CUTOFF = 150.0                  # Hz — "kick drum" band for downbeat
BEAT_MAX_GAP_S = 2.5                 # Maximum gap between beats (seconds)
PHRASE_MIN_BARS = 4                  # Minimum phrase length in bars
PHRASE_MAX_BARS = 32                 # Maximum phrase length in bars
ENERGY_WINDOW_S = 0.05               # RMS window

# ── Onset Detection ─────────────────────────────────────────────────

def _onset_envelope(audio: np.ndarray, sr: float) -> tuple[np.ndarray, float]:
    """Compute onset-strength envelope via spectral flux.

    Returns (envelope, envelope_sample_rate).
    """
    n_fft = N_FFT
    hop = HOP_LENGTH
    noverlap = max(0, n_fft - hop)

    # Mono spectrogram
    f, t, Sxx = scipy_signal.spectrogram(
        audio, fs=sr, nperseg=n_fft, noverlap=noverlap,
        window='hann', mode='magnitude',
    )
    # Spectral flux: sum of positive magnitude differences across frequency
    diff = np.diff(Sxx, axis=1)
    flux = np.sum(np.maximum(diff, 0.0), axis=0)

    # Normalise
    peak = np.max(flux)
    if peak > 0:
        flux = flux / peak

    # Light lowpass to remove jitter
    nyq = sr / hop / 2.0
    cutoff = min(ONSET_SMOOTH_HZ, nyq * 0.95)
    if cutoff > 0 and len(flux) > 6:
        b, a = scipy_signal.butter(2, cutoff / nyq)
        flux = scipy_signal.filtfilt(b, a, flux)

    flux = np.maximum(flux, 0.0)
    onset_sr = sr / hop
    return flux.astype(np.float64), onset_sr


# ── BPM Detection ───────────────────────────────────────────────────

def detect_bpm(
    audio: np.ndarray,
    sr: float,
    *,
    min_bpm: float = BPM_MIN,
    max_bpm: float = BPM_MAX,
) -> tuple[float, float, list[tuple[float, float]]]:
    """Detect BPM from onset-strength autocorrelation.

    Returns:
        (bpm, confidence, candidates) where candidates is a list of
        (bpm, score) sorted by descending score.
    """
    onset, onset_sr = _onset_envelope(audio, sr)
    n = len(onset)

    # Autocorrelation
    onset_c = onset - np.mean(onset)
    ac = np.correlate(onset_c, onset_c, mode='full')
    ac = ac[len(ac) // 2:]
    if ac[0] < 1e-10:
        return 120.0, 0.0, [(120.0, 0.0)]
    ac = ac / ac[0]

    min_lag_frames = max(1, int(onset_sr * 60.0 / max_bpm))
    max_lag_frames = min(n - 1, int(onset_sr * 60.0 / min_bpm))

    if min_lag_frames >= max_lag_frames:
        return 120.0, 0.0, [(120.0, 0.0)]

    # Collect local maxima in autocorrelation
    candidates_raw: list[tuple[float, float, int]] = []  # (bpm, ac_value, lag)
    search_win = 3
    for lag in range(min_lag_frames, max_lag_frames):
        lo = max(0, lag - search_win)
        hi = min(len(ac), lag + search_win + 1)
        if ac[lag] == np.max(ac[lo:hi]) and ac[lag] > 0.08:
            bpm_val = 60.0 * onset_sr / lag
            candidates_raw.append((bpm_val, float(ac[lag]), lag))

    if not candidates_raw:
        candidates_raw.append((120.0, 0.01, int(onset_sr * 60.0 / 120.0)))

    # Sub-harmonic summation scoring with a DJ-friendly tempo prior.
    # Pop/hip-hop/electronic almost always sit in 80-160 BPM. Tempos
    # outside this range get a mild penalty to avoid half-time/double-
    # time misdetection.
    def _tempo_prior(bpm_val: float) -> float:
        if 80.0 <= bpm_val <= 160.0:
            return 1.0
        if 160.0 < bpm_val <= 200.0:
            return 0.88  # Double-time is less likely
        if 60.0 <= bpm_val < 80.0:
            return 0.82  # Half-time is less likely for pop/hip-hop
        return 0.70

    scored: list[tuple[float, float]] = []
    for bpm_val, base_score, lag in candidates_raw:
        score = base_score
        # Harmonic bonus: 2x, 3x, 4x BPM
        for mult in [2, 3, 4]:
            hl = lag * mult
            if hl < len(ac):
                score += float(ac[hl]) * 0.40 / mult
        # Sub-harmonic bonus: 1/2, 1/3 BPM
        for div in [2, 3]:
            sl = lag // div
            if sl >= min_lag_frames:
                score += float(ac[sl]) * 0.25 / div
        # Apply tempo prior
        score *= _tempo_prior(bpm_val)
        scored.append((round(bpm_val, 2), round(score, 4)))

    scored.sort(key=lambda x: x[1], reverse=True)

    best_bpm, best_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.001
    confidence = round(min(0.99, max(0.05, 1.0 - second_score / (best_score + 1e-9))), 3)

    return best_bpm, confidence, scored[:5]


# ── Beat Tracking ───────────────────────────────────────────────────

def _beat_transition_cost(delta_frames: float, target_frames: float) -> float:
    """Penalise beat-interval deviations from target tempo.

    A log-symmetric cost so stretching and compressing by the same ratio
    incur equal penalty.
    """
    ratio = delta_frames / target_frames if target_frames > 0 else 1.0
    dev = ratio - 1.0
    # Gentle quadratic for small deviations, steeper for large ones
    return 80.0 * (dev ** 2) + 120.0 * (abs(dev) ** 3)


def detect_beats(
    audio: np.ndarray,
    sr: float,
    bpm: float,
    *,
    tightness: float = 1.0,
) -> list[float]:
    """Dynamic-programming beat tracker locked to *bpm*.

    Uses the Ellis (2007) DP framework: maximise cumulative onset
    strength while penalising tempo deviations.

    Returns beat times in seconds.
    """
    onset, onset_sr = _onset_envelope(audio, sr)
    n = len(onset)
    if n < 3:
        return [0.0]

    target_spacing = onset_sr * 60.0 / max(bpm, 40.0) * tightness
    local_score = onset.copy().astype(np.float64)

    max_gap = int(onset_sr * BEAT_MAX_GAP_S)

    # Forward DP
    best_score = np.full(n, -1e12, dtype=np.float64)
    best_prev = np.full(n, -1, dtype=np.intp)

    # Seed: first max_gap frames
    best_score[:max_gap] = local_score[:max_gap] * 0.5
    best_prev[:max_gap] = -1

    for i in range(1, n):
        search_start = max(0, i - max_gap)
        for j in range(search_start, i):
            s = best_score[j]
            if s <= -1e11:
                continue
            cost = _beat_transition_cost(i - j, target_spacing)
            candidate = s + local_score[i] - cost
            if candidate > best_score[i]:
                best_score[i] = candidate
                best_prev[i] = j

    # Backward pass — pick best end point in final 2 seconds
    end_margin = int(onset_sr * 2.0)
    end_start = max(0, n - end_margin)
    if end_start >= n:
        end_start = 0
    best_end = end_start + int(np.argmax(best_score[end_start:]))

    beat_frames = []
    idx = best_end
    while idx >= 0:
        beat_frames.append(idx)
        idx = best_prev[idx]
    beat_frames.reverse()

    # Refine each beat: snap to local onset peak (± small window)
    refine_win = max(1, int(onset_sr * 0.020))  # ±20ms
    refined = []
    for f in beat_frames:
        lo = max(0, f - refine_win)
        hi = min(n, f + refine_win + 1)
        peak = lo + int(np.argmax(onset[lo:hi]))
        refined.append(peak)

    beat_times = [round(b / onset_sr, 6) for b in refined]
    return beat_times


# ── Downbeat Detection ──────────────────────────────────────────────

def detect_downbeats(
    beats: list[float],
    audio: np.ndarray,
    sr: float,
) -> tuple[list[int], int]:
    """Determine which beat indices are downbeats (beat 1 of a 4/4 bar).

    Strategy: try each of the 4 possible downbeat offsets, score by
    low-frequency energy at those positions (kick drum tends to land
    on beat 1).  Returns (downbeat_indices, offset).
    """
    n_beats = len(beats)
    if n_beats < 8:
        return list(range(0, n_beats, 4)), 0

    # Low-frequency energy envelope
    nyq = sr / 2.0
    b, a = scipy_signal.butter(2, BASS_CUTOFF / nyq, btype='low')
    bass = scipy_signal.filtfilt(b, a, audio)
    bass_abs = np.abs(bass)

    # For each beat, measure bass energy in a tight window
    beat_bass = np.zeros(n_beats)
    win_s = int(sr * 0.040)  # 40ms window
    for i, bt in enumerate(beats):
        ci = int(bt * sr)
        lo = max(0, ci - win_s)
        hi = min(len(bass_abs), ci + win_s)
        beat_bass[i] = np.max(bass_abs[lo:hi]) if hi > lo else 0.0

    # Score each offset: mean bass energy at that phase
    offsets = np.zeros(4)
    for off in range(4):
        indices = list(range(off, n_beats, 4))
        if indices:
            offsets[off] = np.mean(beat_bass[indices])

    best_offset = int(np.argmax(offsets))
    downbeats = list(range(best_offset, n_beats, 4))
    return downbeats, best_offset


# ── Phrase Analysis ─────────────────────────────────────────────────

def _spectral_novelty(audio: np.ndarray, sr: float) -> tuple[np.ndarray, float]:
    """Compute spectral novelty curve (Foote 2000).

    Uses a log-frequency spectrogram and Gaussian-tapered checkerboard
    kernel to detect structural boundaries.
    """
    n_fft = N_FFT * 2
    hop = HOP_LENGTH * 2
    noverlap = max(0, n_fft - hop)

    f, t, Sxx = scipy_signal.spectrogram(
        audio, fs=sr, nperseg=n_fft, noverlap=noverlap,
        window='hann', mode='magnitude',
    )

    # Log compression
    S_log = np.log1p(Sxx)

    # Gaussian checkerboard kernel along time axis
    kernel_width = 32  # frames (~1.5s at hop=1024)
    half = kernel_width // 2
    t_axis = np.arange(-half, half + 1)
    sigma = half / 3.0
    gauss = np.exp(-0.5 * (t_axis / sigma) ** 2)
    # Checkerboard: positive right lobe, negative left lobe
    kernel = gauss.copy()
    kernel[:half] *= -1.0
    kernel = kernel / np.sum(np.abs(kernel))

    # Convolve along time
    novelty = np.zeros(len(t))
    for freq_bin in range(S_log.shape[0]):
        novelty += np.convolve(S_log[freq_bin, :], kernel, mode='same')

    novelty = np.maximum(novelty, 0.0)
    peak = np.max(novelty)
    if peak > 0:
        novelty = novelty / peak

    novelty_sr = sr / hop
    return novelty, novelty_sr


def _snap_to_bar(time_sec: float, beats: list[float],
                 downbeats: list[int], sr: float) -> float:
    """Snap a candidate time to the nearest downbeat."""
    db_times = [beats[i] for i in downbeats]
    if not db_times:
        return time_sec
    # Find closest downbeat
    idx = min(range(len(db_times)), key=lambda i: abs(db_times[i] - time_sec))
    return db_times[idx]


def _classify_phrase_energy(
    audio: np.ndarray,
    sr: float,
    start_s: float,
    end_s: float,
) -> dict[str, float]:
    """Quick energy + spectral-centroid classification of a phrase window."""
    s0 = max(0, int(start_s * sr))
    s1 = min(len(audio), int(end_s * sr))
    if s1 <= s0 + sr * 2:
        return {"rms": 0.5, "centroid_ratio": 0.5, "label": "Unknown"}

    chunk = audio[s0:s1].astype(np.float64)
    rms = float(np.sqrt(np.mean(chunk ** 2)) + 1e-10)

    # Spectral centroid (approximate via zero-crossing density)
    zcr = float(np.sum(np.abs(np.diff(np.sign(chunk)))) / (2 * len(chunk)))
    zcr_norm = min(1.0, zcr * 30.0)  # Normalise to [0,1] rough range

    # Heuristic label
    if rms < 0.03:
        label = "Breakdown"
    elif rms > 0.15 and zcr_norm > 0.4:
        label = "Chorus"
    elif rms > 0.08:
        label = "Verse"
    else:
        label = "Bridge"

    return {"rms": round(rms, 4), "centroid_ratio": round(zcr_norm, 4), "label": label}


def analyze_phrases(
    audio: np.ndarray,
    sr: float,
    beats: list[float],
    downbeats: list[int],
) -> list[dict]:
    """Detect phrase boundaries and classify each phrase.

    Uses spectral novelty to find structural boundaries, snaps them to
    the nearest downbeat, then merges small fragments into musically
    meaningful sections (minimum ~4 bars, typical DJ phrase length).

    Returns list of {start, end, label, rms, centroid_ratio, bars}.
    """
    novelty, nov_sr = _spectral_novelty(audio, sr)

    # Peak picking on novelty curve
    peak_thresh = 0.10
    min_distance = int(nov_sr * 6.0)  # At least 6s between boundaries (~8 bars at 120BPM)
    peaks, props = scipy_signal.find_peaks(
        novelty, height=peak_thresh, distance=min_distance,
    )

    boundary_times = [0.0]
    for p in peaks:
        bt = p / nov_sr
        # Snap to nearest downbeat
        snapped = _snap_to_bar(bt, beats, downbeats, sr)
        if snapped > boundary_times[-1] + 4.0:  # Minimum 4s segment
            boundary_times.append(snapped)

    duration = len(audio) / sr
    if boundary_times[-1] < duration - 6.0:
        boundary_times.append(duration)

    # Classify each segment
    db_times = [beats[i] for i in downbeats]
    raw_phrases = []
    for i in range(len(boundary_times) - 1):
        t0, t1 = boundary_times[i], boundary_times[i + 1]
        bars = sum(1 for d in db_times if t0 <= d < t1)
        energy_info = _classify_phrase_energy(audio, sr, t0, t1)
        raw_phrases.append({
            "start": round(t0, 3),
            "end": round(t1, 3),
            "duration": round(t1 - t0, 3),
            "bars": bars,
            "label": energy_info["label"],
            "rms": energy_info["rms"],
            "centroid_ratio": energy_info["centroid_ratio"],
        })

    # ── Merge pass: combine adjacent small segments with similar energy ──
    merged: list[dict] = []
    for ph in raw_phrases:
        if not merged:
            merged.append(ph)
            continue
        prev = merged[-1]
        same_class = (prev["label"] == ph["label"] or
                      {prev["label"], ph["label"]}.issubset({"Verse", "Chorus", "Bridge"}))
        similar_energy = abs(prev["rms"] - ph["rms"]) < 0.12
        is_short = ph["bars"] < 6 or prev["bars"] < 6
        if is_short and similar_energy and same_class:
            merged[-1] = {
                "start": prev["start"],
                "end": ph["end"],
                "duration": round(ph["end"] - prev["start"], 3),
                "bars": prev["bars"] + ph["bars"],
                "label": prev["label"] if prev["bars"] >= ph["bars"] else ph["label"],
                "rms": round((prev["rms"] * prev["duration"] + ph["rms"] * ph["duration"]) /
                             max(0.001, prev["duration"] + ph["duration"]), 4),
                "centroid_ratio": round((prev["centroid_ratio"] + ph["centroid_ratio"]) / 2, 4),
            }
        else:
            merged.append(ph)

    return merged


# ── Energy Curve ────────────────────────────────────────────────────

def analyze_energy_curve(audio: np.ndarray, sr: float) -> np.ndarray:
    """RMS energy curve, windowed and downsampled to ~86 Hz for plotting/scoring."""
    win = max(1, int(sr * ENERGY_WINDOW_S))
    hop = win // 2
    n_frames = (len(audio) - win) // hop + 1
    if n_frames < 2:
        return np.array([0.5])
    energy = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop
        chunk = audio[start:start + win].astype(np.float64)
        energy[i] = float(np.sqrt(np.mean(chunk ** 2)) + 1e-10)
    # Normalise to [0,1]
    emax = np.max(energy)
    if emax > 0:
        energy = energy / emax
    return energy.astype(np.float64)


# ── Grid Quality Assessment ─────────────────────────────────────────

def assess_grid_quality(beats: list[float], bpm: float) -> dict:
    """Quantify beat-grid consistency.

    Returns {score, mean_ioi, ioi_std, n_beats} where score ∈ [0,1].
    """
    if len(beats) < 4:
        return {"score": 0.1, "mean_ioi": 0.0, "ioi_std": 0.0, "n_beats": len(beats)}

    iois = np.diff(beats)
    expected = 60.0 / max(bpm, 40.0)

    mean_ioi = float(np.mean(iois))
    std_ioi = float(np.std(iois))

    # Score: how close is mean IOI to expected, and how tight is the spread?
    ratio_error = abs(mean_ioi / expected - 1.0)
    cv = std_ioi / max(mean_ioi, 0.001)  # Coefficient of variation

    score = max(0.0, 1.0 - ratio_error * 5.0 - cv * 8.0)
    score = round(min(1.0, score), 3)

    return {
        "score": score,
        "mean_ioi": round(mean_ioi, 4),
        "ioi_std": round(std_ioi, 4),
        "n_beats": len(beats),
    }


# ── Transition Alignment ────────────────────────────────────────────

def find_nearest_beat(time_sec: float, beats: list[float]) -> float:
    """Return the closest beat time."""
    if not beats:
        return time_sec
    idx = min(range(len(beats)), key=lambda i: abs(beats[i] - time_sec))
    return beats[idx]


def find_nearest_downbeat(time_sec: float, beats: list[float],
                          downbeats: list[int]) -> float:
    """Return the closest downbeat time."""
    db_times = [beats[i] for i in downbeats]
    if not db_times:
        return find_nearest_beat(time_sec, beats)
    idx = min(range(len(db_times)), key=lambda i: abs(db_times[i] - time_sec))
    return db_times[idx]


def transition_alignment_score(
    exit_time: float,
    entry_time: float,
    a_beats: list[float],
    b_beats: list[float],
    a_downbeats: list[int],
    b_downbeats: list[int],
    a_phrases: list[dict],
    b_phrases: list[dict],
) -> dict:
    """Score a transition point pair on beat-grid and phrase alignment.

    Returns {score, exit_on_beat1, entry_on_beat1, exit_phrase_label,
             entry_phrase_label, beat_offset_ms, details}.
    """
    details: list[str] = []
    score = 0.0

    # 1. Beat alignment: how close is each point to the nearest beat?
    a_nearest = find_nearest_beat(exit_time, a_beats)
    b_nearest = find_nearest_beat(entry_time, b_beats)
    a_off = abs(exit_time - a_nearest)
    b_off = abs(entry_time - b_nearest)

    beat_score = 0.0
    if a_off < 0.015 and b_off < 0.015:
        beat_score = 0.25
        details.append("both exit/entry on beat")
    elif a_off < 0.030 and b_off < 0.030:
        beat_score = 0.15
        details.append(f"near beat (A:{a_off*1000:.0f}ms B:{b_off*1000:.0f}ms)")
    elif a_off < 0.060:
        beat_score = 0.06
        details.append(f"loose beat align ({a_off*1000:.0f}ms)")
    else:
        details.append(f"off-beat exit ({a_off*1000:.0f}ms)")
    score += beat_score

    # 2. Downbeat alignment (beat 1): strongest phrase boundary
    a_db = find_nearest_downbeat(exit_time, a_beats, a_downbeats)
    b_db = find_nearest_downbeat(entry_time, b_beats, b_downbeats)
    a_db_off = abs(exit_time - a_db)
    b_db_off = abs(entry_time - b_db)

    db_score = 0.0
    if a_db_off < 0.020 and b_db_off < 0.020:
        db_score = 0.22
        details.append("both on downbeat (beat 1)")
    elif a_db_off < 0.040:
        db_score = 0.12
        details.append("exit near downbeat")
    elif b_db_off < 0.040:
        db_score = 0.10
        details.append("entry near downbeat")
    score += db_score

    # 3. Phrase boundary bonus
    a_phrase_label = "Unknown"
    b_phrase_label = "Unknown"
    for ph in a_phrases:
        if ph["start"] <= exit_time < ph["end"]:
            a_phrase_label = ph["label"]
            # Bonus if exiting near end of phrase
            remaining = ph["end"] - exit_time
            if 0 < remaining < 4.0:
                score += 0.12
                details.append(f"exit near phrase end ({a_phrase_label}, {remaining:.1f}s remain)")
            break

    for ph in b_phrases:
        if ph["start"] <= entry_time < ph["end"]:
            b_phrase_label = ph["label"]
            # Bonus if entering near start of phrase
            into = entry_time - ph["start"]
            if 0 < into < 6.0:
                score += 0.12
                details.append(f"entry near phrase start ({b_phrase_label}, {into:.1f}s in)")
            break

    # 4. Phrase label quality
    good_exit_labels = {"Outro", "Bridge", "Breakdown", "Chorus"}
    good_entry_labels = {"Intro", "Verse", "Build", "Breakdown", "PreChorus"}
    if a_phrase_label in good_exit_labels:
        score += 0.08
        details.append(f"good exit label: {a_phrase_label}")
    if b_phrase_label in good_entry_labels:
        score += 0.08
        details.append(f"good entry label: {b_phrase_label}")

    a_db_time = a_beats[a_downbeats[0]] if a_downbeats and a_downbeats[0] < len(a_beats) else 0.0
    b_db_time = b_beats[b_downbeats[0]] if b_downbeats and b_downbeats[0] < len(b_beats) else 0.0

    return {
        "score": round(min(1.0, score), 3),
        "exit_beat_offset_ms": round(float(a_off) * 1000, 1),
        "entry_beat_offset_ms": round(float(b_off) * 1000, 1),
        "exit_on_downbeat": bool(a_db_off < 0.025),
        "entry_on_downbeat": bool(b_db_off < 0.025),
        "exit_phrase_label": a_phrase_label,
        "entry_phrase_label": b_phrase_label,
        "details": details,
    }


# ── Master Analysis ─────────────────────────────────────────────────

def analyze_track(
    source: str | Path | np.ndarray,
    sr: float = 44100,
    *,
    precomputed: dict | None = None,
) -> dict[str, Any]:
    """Run complete audio analysis on a track.

    Args:
        source: File path or mono/stereo numpy array.
        sr: Sample rate (ignored if source is a file path).
        precomputed: Optional dict of pre-existing analysis fields to
                     merge in (e.g. from Jetson API). Fields like bpm,
                     beats, energy, key, camelot are preserved if present.

    Returns a dict with keys:
        bpm, bpm_confidence, bpm_candidates,
        beats, downbeats, downbeat_indices, downbeat_offset,
        phrases, energy_curve, energy_mean,
        grid_quality, duration
    """
    # Load
    if isinstance(source, (str, Path)):
        import soundfile as sf
        data, sr = sf.read(str(source), always_2d=False)
        if data.ndim > 1:
            audio_mono = np.mean(data.astype(np.float64), axis=1)
        else:
            audio_mono = data.astype(np.float64)
    else:
        data = np.asarray(source, dtype=np.float64)
        if data.ndim > 1:
            audio_mono = np.mean(data, axis=1)
        else:
            audio_mono = data

    duration = len(audio_mono) / sr

    # Merge precomputed values when available (e.g. Jetson metadata)
    pc = precomputed or {}

    # BPM
    if "bpm" in pc and pc["bpm"] > 0:
        bpm = float(pc["bpm"])
        bpm_conf = float(pc.get("bpm_confidence", 0.8))
        bpm_candidates = pc.get("bpm_candidates", [(bpm, bpm_conf)])
    else:
        bpm, bpm_conf, bpm_candidates = detect_bpm(audio_mono, sr)

    # Beats
    if "beats" in pc and len(pc["beats"]) >= 4:
        beats = [float(b) for b in pc["beats"]]
    else:
        beats = detect_beats(audio_mono, sr, bpm)

    # Downbeats
    downbeats, db_offset = detect_downbeats(beats, audio_mono, sr)

    # Phrases
    phrases = analyze_phrases(audio_mono, sr, beats, downbeats)

    # Energy
    energy_curve = analyze_energy_curve(audio_mono, sr)
    energy_mean = float(np.mean(energy_curve))

    # Grid quality
    grid_quality = assess_grid_quality(beats, bpm)

    return {
        "bpm": bpm,
        "bpm_confidence": bpm_conf,
        "bpm_candidates": bpm_candidates,
        "beats": beats,
        "downbeats": [beats[i] for i in downbeats],
        "downbeat_indices": downbeats,
        "downbeat_offset": db_offset,
        "phrases": phrases,
        "energy_curve": energy_curve.tolist() if isinstance(energy_curve, np.ndarray) else energy_curve,
        "energy_mean": round(energy_mean, 4),
        "grid_quality": grid_quality,
        "duration": round(duration, 3),
    }
