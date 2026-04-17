"""Commercial-grade BPM / beatgrid analysis engine.

Architecture:
    madmom (offline, BSD)           鈥?primary beat/downbeat detector
    BeatNet (real-time, MIT)        鈥?secondary detector + live correction
    librosa tempogram              鈥?auxiliary BPM verification
    Self-built beatgrid alignment  鈥?snap beats to uniform grid
    Confidence scoring layer       鈥?multi-engine cross-validation
    Human correction API           鈥?manual override support

All components use MIT/BSD/ISC licenses 鈥?no commercial restrictions.
"""
from __future__ import annotations

import collections
import collections.abc
import logging
from dataclasses import dataclass, field

import numpy as np

# Python 3.10+ removed collections.MutableSequence etc.
# madmom 0.16.1 still uses them 鈥?patch before importing.
for _attr in ("MutableSequence", "MutableMapping", "MutableSet",
              "Mapping", "Sequence", "Iterable", "Iterator"):
    if not hasattr(collections, _attr) and hasattr(collections.abc, _attr):
        setattr(collections, _attr, getattr(collections.abc, _attr))

# NumPy 1.24+ removed deprecated aliases used by madmom 0.16.1.
for _alias, _real in (("float", np.float64), ("int", np.int_),
                       ("complex", np.complex128), ("object", np.object_),
                       ("bool", np.bool_), ("str", np.str_)):
    if not hasattr(np, _alias):
        setattr(np, _alias, _real)

logger = logging.getLogger(__name__)

# 鈹€鈹€ Result dataclass 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@dataclass
class BeatResult:
    """Output of the beat analysis engine."""
    bpm: float
    beat_points: list[float]          # aligned beatgrid timestamps (seconds)
    downbeats: list[float]            # downbeat timestamps (bar starts)
    grid_offset: float                # beatgrid phase offset (seconds)
    grid_interval: float              # beatgrid interval = 60 / bpm
    confidence: float                 # overall confidence 0-1
    confidence_details: dict = field(default_factory=dict)
    engines_used: list[str] = field(default_factory=list)
    needs_review: bool = False        # True if confidence < threshold
    raw_results: dict = field(default_factory=dict)  # per-engine raw results

    def __post_init__(self):
        """Coerce numpy types to Python builtins for DB compatibility."""
        self.bpm = float(self.bpm)
        self.beat_points = [float(x) for x in self.beat_points]
        self.downbeats = [float(x) for x in self.downbeats]
        self.grid_offset = float(self.grid_offset)
        self.grid_interval = float(self.grid_interval)
        self.confidence = float(self.confidence)
        self.needs_review = bool(self.needs_review)


# 鈹€鈹€ Engine availability checks 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

_HAS_ESSENTIA: bool | None = None
_HAS_MADMOM: bool | None = None
_HAS_BEATNET: bool | None = None


def _essentia_available() -> bool:
    global _HAS_ESSENTIA
    if _HAS_ESSENTIA is None:
        try:
            import essentia.standard  # noqa: F401
            _HAS_ESSENTIA = True
        except Exception:
            _HAS_ESSENTIA = False
            logger.info("essentia not available")
    return _HAS_ESSENTIA


def _madmom_available() -> bool:
    global _HAS_MADMOM
    if _HAS_MADMOM is None:
        try:
            import madmom  # noqa: F401
            _HAS_MADMOM = True
        except Exception:
            _HAS_MADMOM = False
            logger.info("madmom not available")
    return _HAS_MADMOM


def _beatnet_available() -> bool:
    global _HAS_BEATNET
    if _HAS_BEATNET is None:
        try:
            from BeatNet.BeatNet import BeatNet  # noqa: F401
            _HAS_BEATNET = True
        except Exception:
            _HAS_BEATNET = False
            logger.info("BeatNet not available")
    return _HAS_BEATNET


# 鈹€鈹€ Individual engine runners 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def _run_essentia(file_path: str) -> dict:
    """Run Essentia RhythmExtractor2013 + PercivalBpmEstimator.

    Essentia is the same engine used by most online BPM detection tools
    (compiled to WebAssembly for browser use). Using the Python binding
    gives identical results to the WASM version.

    Returns dict with bpm, beats, confidence, percival_bpm, bpm_histogram.
    """
    import essentia.standard as es

    loader = es.MonoLoader(filename=file_path, sampleRate=44100)
    audio = loader()

    # Primary: RhythmExtractor2013 (multifeature method)
    rhythm = es.RhythmExtractor2013(method="multifeature")
    bpm, beats, confidence, estimates, bpm_intervals = rhythm(audio)

    beat_times = [round(float(t), 3) for t in beats]

    # Compute regularity from beat intervals
    if len(beats) > 1:
        intervals = np.diff(beats)
        regularity = 1.0 - min(1.0, float(np.std(intervals) / (np.mean(intervals) + 1e-9)))
    else:
        regularity = 0.0

    # Secondary: PercivalBpmEstimator (independent verification)
    percival = es.PercivalBpmEstimator()
    percival_bpm = float(percival(audio))

    # Build BPM histogram from beat intervals for metrical level analysis
    bpm_histogram: dict[int, int] = {}
    if len(bpm_intervals) > 0:
        hist_bpms = 60.0 / bpm_intervals[bpm_intervals > 0]
        for b in hist_bpms:
            key = int(round(b))
            bpm_histogram[key] = bpm_histogram.get(key, 0) + 1

    return {
        "bpm": round(float(bpm), 2),
        "percival_bpm": round(percival_bpm, 2),
        "beats": beat_times,
        "downbeats": [],  # Essentia beat tracker doesn't separate downbeats
        "confidence": round(float(confidence), 4),
        "regularity": round(float(regularity), 3),
        "bpm_histogram": bpm_histogram,
    }


def _run_madmom(file_path: str) -> dict:
    """Run madmom RNN beat/downbeat tracking. Returns dict with bpm, beats, downbeats."""
    from madmom.features.beats import DBNBeatTrackingProcessor, RNNBeatProcessor
    from madmom.features.downbeats import DBNDownBeatTrackingProcessor, RNNDownBeatProcessor

    beat_act = RNNBeatProcessor()(file_path)
    beats = DBNBeatTrackingProcessor(fps=100)(beat_act)
    beat_times = np.array([float(t) for t in beats])

    try:
        db_act = RNNDownBeatProcessor()(file_path)
        db_result = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=100)(db_act)
        downbeats = [round(float(row[0]), 3) for row in db_result if int(round(row[1])) == 1]
    except Exception:
        logger.warning("madmom downbeat detection failed, using beats only")
        downbeats = []

    if len(beat_times) > 1:
        intervals = np.diff(beat_times)
        bpm = 60.0 / float(np.median(intervals))
        # Beat regularity: low std/mean ratio = stable tempo
        regularity = 1.0 - min(1.0, float(np.std(intervals) / (np.mean(intervals) + 1e-9)))
    else:
        bpm = 120.0
        regularity = 0.0

    return {
        "bpm": round(bpm, 2),
        "beats": [round(float(t), 3) for t in beat_times],
        "downbeats": downbeats,
        "regularity": round(regularity, 3),
    }


def _run_beatnet(file_path: str) -> dict:
    """Run BeatNet offline inference. Returns dict with bpm, beats, downbeats."""
    from BeatNet.BeatNet import BeatNet

    # mode=1: offline, inference_model must be "DBN" for offline mode
    estimator = BeatNet(
        1,
        mode="offline",
        inference_model="DBN",
        plot=[],
        thread=False,
    )
    output = estimator.process(file_path)

    # BeatNet output: Nx2 array, col0=time, col1=beat_type (1=downbeat, 2=beat)
    if output is None or len(output) == 0:
        return {"bpm": 0.0, "beats": [], "downbeats": [], "regularity": 0.0}

    all_times = [float(row[0]) for row in output]
    downbeats = [float(row[0]) for row in output if int(row[1]) == 1]
    beat_times = np.array(all_times)

    if len(beat_times) > 1:
        intervals = np.diff(beat_times)
        bpm = 60.0 / float(np.median(intervals))
        regularity = 1.0 - min(1.0, float(np.std(intervals) / (np.mean(intervals) + 1e-9)))
    else:
        bpm = 0.0
        regularity = 0.0

    return {
        "bpm": round(bpm, 2),
        "beats": [round(t, 3) for t in all_times],
        "downbeats": [round(t, 3) for t in downbeats],
        "regularity": round(regularity, 3),
    }


def _run_librosa_tempogram(y: np.ndarray, sr: int) -> dict:
    """Run librosa tempogram analysis for BPM verification."""
    import librosa

    # Standard beat_track
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    bpm_basic = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])

    # Also run beat_track with a low start_bpm prior to catch half-time tempos
    tempo_low, _ = librosa.beat.beat_track(y=y, sr=sr, start_bpm=80)
    bpm_low_prior = float(tempo_low) if not hasattr(tempo_low, "__len__") else float(tempo_low[0])

    # Tempogram for spectral clarity
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempogram = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr)

    # Global tempo from tempogram (autocorrelation peak)
    ac_global = np.mean(tempogram, axis=1)
    # Skip first few bins (very low BPM)
    freqs = librosa.tempo_frequencies(tempogram.shape[0], sr=sr)
    valid = (freqs >= 60) & (freqs <= 200)
    if np.any(valid):
        ac_valid = ac_global.copy()
        ac_valid[~valid] = 0
        peak_idx = np.argmax(ac_valid)
        bpm_tempogram = float(freqs[peak_idx])
        # Clarity: ratio of peak to mean
        peak_val = ac_valid[peak_idx]
        mean_val = float(np.mean(ac_valid[valid]))
        clarity = min(1.0, peak_val / (mean_val + 1e-9) / 5.0)

        # Collect top N tempogram peaks for ambiguity resolution
        valid_indices = np.where(valid)[0]
        valid_strengths = ac_global[valid_indices]
        top_n = min(8, len(valid_indices))
        top_indices = valid_indices[np.argsort(valid_strengths)[-top_n:][::-1]]
        tempogram_peaks = [(round(float(freqs[i]), 1), round(float(ac_global[i]), 4))
                           for i in top_indices]
    else:
        bpm_tempogram = bpm_basic
        clarity = 0.5
        tempogram_peaks = []

    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    return {
        "bpm_beat_track": round(bpm_basic, 2),
        "bpm_low_prior": round(bpm_low_prior, 2),
        "bpm_tempogram": round(bpm_tempogram, 2),
        "clarity": round(clarity, 3),
        "beats": [round(float(t), 3) for t in beat_times],
        "tempogram_peaks": tempogram_peaks,
    }


# 鈹€鈹€ Beatgrid alignment 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def _align_beatgrid(
    beat_times: np.ndarray,
    bpm: float,
    duration: float,
) -> tuple[list[float], float, float]:
    """Snap detected beats to a uniform grid.

    Returns (grid_beats, grid_offset, grid_interval).
    The grid is defined by: grid[i] = offset + i * interval
    """
    if len(beat_times) < 2 or bpm <= 0:
        return list(beat_times), 0.0, 0.5

    interval = 60.0 / bpm

    # Find optimal phase offset by minimizing total snap distance.
    # Test offsets in 1ms steps within one beat interval.
    best_offset = 0.0
    best_error = float("inf")
    test_offsets = np.linspace(0, interval, num=int(interval * 1000), endpoint=False)

    for offset in test_offsets:
        # For each detected beat, find distance to nearest grid point
        grid_indices = np.round((beat_times - offset) / interval)
        grid_points = offset + grid_indices * interval
        error = float(np.mean(np.abs(beat_times - grid_points)))
        if error < best_error:
            best_error = error
            best_offset = float(offset)

    # Generate the full beatgrid from start to end
    first_grid = best_offset
    # Extend grid before the first detected beat if needed
    while first_grid > interval:
        first_grid -= interval

    grid_beats = []
    t = first_grid
    while t <= duration + interval * 0.5:
        if t >= 0:
            grid_beats.append(round(t, 3))
        t += interval

    return grid_beats, round(best_offset, 4), round(interval, 6)


# 鈹€鈹€ Half/double BPM correction 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def _correct_octave_bpm(candidates: list[float]) -> float:
    """Given multiple BPM estimates, resolve half/double ambiguity.

    Prefers BPM in the 80-160 range (typical for most modern music).
    Uses voting when multiple engines agree.
    """
    if not candidates:
        return 120.0

    # Normalize all candidates to 70-170 range
    normalized = []
    for bpm in candidates:
        if bpm <= 0:
            continue
        b = bpm
        while b < 70:
            b *= 2
        while b > 170:
            b /= 2
        normalized.append(b)

    if not normalized:
        return candidates[0] if candidates else 120.0

    # Cluster normalized candidates (within 4% = ~5 BPM at 120)
    normalized.sort()
    clusters: list[list[float]] = [[normalized[0]]]
    for b in normalized[1:]:
        if abs(b - clusters[-1][-1]) / clusters[-1][-1] < 0.04:
            clusters[-1].append(b)
        else:
            clusters.append([b])

    # Pick the largest cluster, break ties by proximity to 120 BPM
    best_cluster = max(clusters, key=lambda c: (len(c), -abs(np.mean(c) - 120)))
    return round(float(np.median(best_cluster)), 1)


# 鈹€鈹€ Perceptual metrical level selection 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def _onset_periodicity(onset_env: np.ndarray, lag: int) -> float:
    """Normalized autocorrelation of onset envelope at a specific lag.

    Returns a value in [-1, 1] where higher means stronger periodicity
    at the given lag (tempo period).
    """
    n = len(onset_env) - lag
    if n <= lag:  # need at least 2 full periods
        return 0.0
    x1 = onset_env[:n]
    x2 = onset_env[lag:lag + n]
    m1, m2 = float(np.mean(x1)), float(np.mean(x2))
    s1, s2 = float(np.std(x1)), float(np.std(x2))
    if s1 * s2 < 1e-9:
        return 0.0
    return float(np.mean((x1 - m1) * (x2 - m2)) / (s1 * s2))


def _select_perceptual_tempo(
    bpm: float,
    y: np.ndarray,
    sr: int,
) -> float:
    """Select perceptually correct metrical level using sub-band onset analysis.

    Beat trackers can lock onto a metrical level that differs from what
    listeners perceive (e.g., hi-hat rate instead of kick pattern).
    This analyses onset periodicity in two frequency bands:

      - Low-frequency (<300 Hz): kick/bass pattern = perceived tempo
      - Full band: overall rhythmic texture

    Compares onset autocorrelation at the detected BPM vs metrical
    alternatives (脳2/3, 脳1/2, 脳3/2, 脳2). The BPM with strongest
    low-band periodicity wins, with a small bias toward the engine BPM.
    """
    import librosa
    from scipy.signal import butter, sosfilt

    # Generate metrical-level candidates
    candidates = {round(bpm, 1)}
    for ratio in [2 / 3, 0.5, 1.5, 2.0]:
        alt = bpm * ratio
        if 75 <= alt <= 200:
            candidates.add(round(alt, 1))

    if len(candidates) <= 1:
        return bpm

    hop_length = 512
    fps = sr / hop_length

    # Full-band onset envelope
    onset_full = librosa.onset.onset_strength(y=y, sr=sr)

    # Low-band onset envelope (<300 Hz) 鈥?kick/bass defines perceived tempo
    try:
        sos = butter(4, 300, btype='low', fs=sr, output='sos')
        y_low = sosfilt(sos, y.astype(np.float64))
        onset_low = librosa.onset.onset_strength(y=y_low.astype(np.float32), sr=sr)
    except Exception:
        onset_low = onset_full  # fallback

    scores: dict[float, float] = {}
    for c_bpm in candidates:
        lag = int(round(60.0 / c_bpm * fps))
        if lag <= 0 or lag >= len(onset_full) // 4:
            continue

        ac_full = _onset_periodicity(onset_full, lag)
        ac_low = _onset_periodicity(onset_low, lag)

        # Low band weighted higher: bass defines perceived tempo
        score = 0.35 * ac_full + 0.65 * ac_low

        # Small bias for the engine-detected BPM (trust ML models)
        if abs(c_bpm - bpm) / bpm < 0.02:
            score += 0.05

        scores[c_bpm] = round(score, 4)

    if not scores:
        return bpm

    best = max(scores, key=scores.get)  # type: ignore[arg-type]

    # Only switch away from engine BPM if alternative is meaningfully better
    engine_score = scores.get(round(bpm, 1), 0)
    if best != round(bpm, 1) and scores[best] - engine_score < 0.02:
        logger.info("Perceptual tempo: %.1f (%.4f) not clearly better than "
                    "engine %.1f (%.4f) 鈥?keeping engine BPM",
                    best, scores[best], bpm, engine_score)
        return bpm

    if best != round(bpm, 1):
        logger.info("Perceptual tempo correction: %.1f 鈫?%.1f (scores: %s)",
                    bpm, best, scores)

    return best


# 鈹€鈹€ Confidence scoring 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

REVIEW_THRESHOLD = 0.70


def _compute_confidence(
    engine_results: dict[str, dict],
    final_bpm: float,
) -> tuple[float, dict]:
    """Compute overall confidence from multi-engine results.

    Factors:
    1. Cross-engine BPM agreement (accounts for 2:1 and 3:2 relationships)
    2. Beat regularity (per-engine)
    3. Tempogram spectral clarity
    4. Number of engines that ran successfully
    """
    details: dict[str, float] = {}
    weights: list[tuple[float, float]] = []

    # 1. Cross-engine BPM agreement
    bpms = []
    for name, res in engine_results.items():
        if "bpm" in res and res["bpm"] > 0:
            bpms.append(res["bpm"])
        if "bpm_beat_track" in res and res["bpm_beat_track"] > 0:
            bpms.append(res["bpm_beat_track"])

    if len(bpms) >= 2:
        # Normalize to final_bpm's metrical level for comparison.
        # An engine BPM is "agreeing" if it (or a metrical variant) is close.
        norm_bpms = []
        for b in bpms:
            # Find the variant of b closest to final_bpm
            best_variant = b
            best_dist = abs(b - final_bpm)
            for ratio in [0.5, 2 / 3, 3 / 4, 1.0, 4 / 3, 3 / 2, 2.0]:
                v = b * ratio
                d = abs(v - final_bpm)
                if d < best_dist:
                    best_dist = d
                    best_variant = v
            norm_bpms.append(best_variant)
        max_dev = max(abs(b - final_bpm) / final_bpm for b in norm_bpms)
        agreement = max(0, 1.0 - max_dev * 10)  # 10% dev 鈫?0.0 confidence
        details["engine_agreement"] = round(agreement, 3)
        weights.append((agreement, 0.35))
    else:
        details["engine_agreement"] = 0.5
        weights.append((0.5, 0.35))

    # 2. Beat regularity (average across engines)
    regularities = [res.get("regularity", 0.5) for res in engine_results.values()
                    if "regularity" in res]
    if regularities:
        avg_reg = float(np.mean(regularities))
        details["beat_regularity"] = round(avg_reg, 3)
        weights.append((avg_reg, 0.30))
    else:
        details["beat_regularity"] = 0.5
        weights.append((0.5, 0.30))

    # 3. Tempogram clarity
    librosa_res = engine_results.get("librosa", {})
    clarity = librosa_res.get("clarity", 0.5)
    details["tempogram_clarity"] = round(clarity, 3)
    weights.append((clarity, 0.20))

    # 4. Engine coverage (more engines = higher confidence)
    n_engines = len(engine_results)
    coverage = min(1.0, n_engines / 3.0)
    details["engine_coverage"] = round(coverage, 3)
    weights.append((coverage, 0.15))

    # Weighted average
    total_w = sum(w for _, w in weights)
    confidence = sum(v * w for v, w in weights) / total_w if total_w > 0 else 0.5

    return round(confidence, 3), details


# 鈹€鈹€ Downbeat alignment 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def _align_downbeats(
    grid_beats: list[float],
    raw_downbeats: list[float],
    beats_per_bar: int = 4,
) -> list[float]:
    """Align downbeats to the beatgrid. Every `beats_per_bar` grid beats = 1 downbeat.

    Uses detected downbeats to find the best phase within the bar.
    """
    if not grid_beats:
        return raw_downbeats

    grid_arr = np.array(grid_beats)

    if not raw_downbeats:
        # No downbeats detected 鈥?default to every Nth beat starting from 0
        return [grid_beats[i] for i in range(0, len(grid_beats), beats_per_bar)]

    # Find best bar phase: which beat index mod beats_per_bar aligns with detected downbeats
    best_phase = 0
    best_score = -1.0
    db_arr = np.array(raw_downbeats)

    for phase in range(beats_per_bar):
        candidates = grid_arr[phase::beats_per_bar]
        if len(candidates) == 0:
            continue
        # Score: sum of matches (detected downbeat within 100ms of grid downbeat)
        score = 0.0
        for db in db_arr:
            min_dist = float(np.min(np.abs(candidates - db)))
            if min_dist < 0.1:
                score += 1.0
            elif min_dist < 0.2:
                score += 0.5
        if score > best_score:
            best_score = score
            best_phase = phase

    return [grid_beats[i] for i in range(best_phase, len(grid_beats), beats_per_bar)]


# 鈹€鈹€ Main entry point 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def analyze_beats(
    file_path: str,
    y: np.ndarray,
    sr: int,
    duration: float,
) -> BeatResult:
    """Run multi-engine beat analysis with beatgrid alignment and confidence scoring.

    Engine priority:
    1. essentia (RhythmExtractor2013 + Percival 鈥?industry standard, same as online tools)
    2. madmom (RNN, strong cross-validation)
    3. librosa (tempogram, auxiliary verification + ambiguity resolution data)
    """
    engine_results: dict[str, dict] = {}
    engines_used: list[str] = []
    all_raw_downbeats: list[list[float]] = []

    # 鈹€鈹€ Engine 1: Essentia (primary 鈥?same as online BPM tools) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    if _essentia_available():
        try:
            res = _run_essentia(file_path)
            engine_results["essentia"] = res
            engines_used.append("essentia")
            logger.info("essentia: BPM=%.1f, percival=%.1f, %d beats, confidence=%.3f",
                        res["bpm"], res["percival_bpm"], len(res["beats"]),
                        res["confidence"])
        except Exception:
            logger.warning("essentia engine failed", exc_info=True)

    # 鈹€鈹€ Engine 2: madmom 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    if _madmom_available():
        try:
            res = _run_madmom(file_path)
            engine_results["madmom"] = res
            engines_used.append("madmom")
            all_raw_downbeats.append(res["downbeats"])
            logger.info("madmom: BPM=%.1f, %d beats, regularity=%.2f",
                        res["bpm"], len(res["beats"]), res["regularity"])
        except Exception:
            logger.warning("madmom engine failed", exc_info=True)

    # 鈹€鈹€ Engine 2: BeatNet 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    if _beatnet_available():
        try:
            res = _run_beatnet(file_path)
            if res["bpm"] > 0:
                engine_results["beatnet"] = res
                engines_used.append("beatnet")
                all_raw_downbeats.append(res["downbeats"])
                logger.info("BeatNet: BPM=%.1f, %d beats, regularity=%.2f",
                            res["bpm"], len(res["beats"]), res["regularity"])
        except Exception:
            logger.warning("BeatNet engine failed", exc_info=True)

    # 鈹€鈹€ Engine 3: librosa (always available) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    try:
        res = _run_librosa_tempogram(y, sr)
        engine_results["librosa"] = res
        engines_used.append("librosa")
        logger.info("librosa: beat_track=%.1f, tempogram=%.1f, clarity=%.2f",
                    res["bpm_beat_track"], res["bpm_tempogram"], res["clarity"])
    except Exception:
        logger.warning("librosa tempogram failed", exc_info=True)

    # 鈹€鈹€ Resolve BPM (multi-engine voting + octave correction) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    bpm_candidates = []
    for name, res in engine_results.items():
        if "bpm" in res and res["bpm"] > 0:
            bpm_candidates.append(res["bpm"])
        if "percival_bpm" in res and res["percival_bpm"] > 0:
            bpm_candidates.append(res["percival_bpm"])
        if "bpm_beat_track" in res and res["bpm_beat_track"] > 0:
            bpm_candidates.append(res["bpm_beat_track"])
        if "bpm_low_prior" in res and res["bpm_low_prior"] > 0:
            bpm_candidates.append(res["bpm_low_prior"])
        if "bpm_tempogram" in res and res["bpm_tempogram"] > 0:
            bpm_candidates.append(res["bpm_tempogram"])

    final_bpm = _correct_octave_bpm(bpm_candidates)

    # 鈹€鈹€ Post-correction: perceptual metrical level selection 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    final_bpm = _select_perceptual_tempo(final_bpm, y, sr)

    # 鈹€鈹€ Select best raw beats for grid alignment 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    # Prefer essentia > madmom > beatnet > librosa based on regularity
    best_beats: np.ndarray | None = None
    for name in ["essentia", "madmom", "beatnet", "librosa"]:
        if name in engine_results and engine_results[name].get("beats"):
            best_beats = np.array(engine_results[name]["beats"])
            break
    if best_beats is None:
        best_beats = np.array([0.0])

    # 鈹€鈹€ Align beatgrid 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    grid_beats, grid_offset, grid_interval = _align_beatgrid(best_beats, final_bpm, duration)

    # 鈹€鈹€ Merge downbeats and align to grid 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    # Use madmom downbeats as primary, beatnet as secondary
    raw_downbeats = all_raw_downbeats[0] if all_raw_downbeats else []
    aligned_downbeats = _align_downbeats(grid_beats, raw_downbeats)

    # 鈹€鈹€ Compute confidence 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    confidence, conf_details = _compute_confidence(engine_results, final_bpm)
    needs_review = confidence < REVIEW_THRESHOLD

    if needs_review:
        logger.warning("Low confidence (%.2f) for %s 鈥?flagged for manual review",
                       confidence, file_path)

    return BeatResult(
        bpm=final_bpm,
        beat_points=grid_beats,
        downbeats=aligned_downbeats,
        grid_offset=grid_offset,
        grid_interval=grid_interval,
        confidence=confidence,
        confidence_details=conf_details,
        engines_used=engines_used,
        needs_review=needs_review,
        raw_results={k: {"bpm": v.get("bpm", v.get("bpm_beat_track", 0))}
                     for k, v in engine_results.items()},
    )


# 鈹€鈹€ Real-time beat correction (BeatNet streaming) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


class RealtimeBeatCorrector:
    """Lightweight wrapper for BeatNet's online/streaming mode.

    Used during playback to correct beatgrid drift in real-time.
    Call `update(audio_chunk)` with short audio buffers (~100ms).
    """

    def __init__(self, initial_bpm: float, initial_offset: float):
        self.bpm = initial_bpm
        self.offset = initial_offset
        self.interval = 60.0 / initial_bpm if initial_bpm > 0 else 0.5
        self._estimator = None
        self._corrections: list[float] = []

    def _init_beatnet(self) -> bool:
        if not _beatnet_available():
            return False
        try:
            from BeatNet.BeatNet import BeatNet
            self._estimator = BeatNet(
                1,
                mode="online",
                inference_model="PF",
                plot=[],
                thread=False,
            )
            return True
        except Exception:
            logger.warning("Failed to init BeatNet online mode", exc_info=True)
            return False

    def get_correction(self) -> dict:
        """Return accumulated correction statistics."""
        if not self._corrections:
            return {"drift_ms": 0.0, "corrected_bpm": self.bpm, "n_corrections": 0}

        avg_drift = float(np.mean(self._corrections)) * 1000  # ms
        return {
            "drift_ms": round(avg_drift, 1),
            "corrected_bpm": self.bpm,
            "n_corrections": len(self._corrections),
        }


# 鈹€鈹€ Manual beat correction helpers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def apply_manual_correction(
    current: BeatResult,
    corrected_bpm: float | None = None,
    corrected_offset: float | None = None,
    corrected_downbeat_phase: int | None = None,
    duration: float = 0.0,
) -> BeatResult:
    """Apply manual corrections (from human review) to a BeatResult.

    Args:
        current: The auto-detected BeatResult.
        corrected_bpm: Override BPM (e.g. user tapped 128.0).
        corrected_offset: Override grid phase offset in seconds.
        corrected_downbeat_phase: Override downbeat phase (0-3 for 4/4).
        duration: Track duration for regenerating the grid.
    """
    bpm = corrected_bpm if corrected_bpm is not None else current.bpm
    offset = corrected_offset if corrected_offset is not None else current.grid_offset

    if duration <= 0:
        duration = current.beat_points[-1] + 1.0 if current.beat_points else 180.0

    # Regenerate beatgrid with corrected parameters
    interval = 60.0 / bpm
    grid_beats = []
    t = offset
    while t < 0:
        t += interval
    while t <= duration + interval * 0.5:
        grid_beats.append(round(t, 3))
        t += interval

    # Regenerate downbeats
    phase = corrected_downbeat_phase if corrected_downbeat_phase is not None else 0
    downbeats = [grid_beats[i] for i in range(phase, len(grid_beats), 4)]

    return BeatResult(
        bpm=round(bpm, 1),
        beat_points=grid_beats,
        downbeats=downbeats,
        grid_offset=round(offset, 4),
        grid_interval=round(interval, 6),
        confidence=1.0,  # Human-verified = max confidence
        confidence_details={"source": "manual_correction"},
        engines_used=current.engines_used + ["manual"],
        needs_review=False,
        raw_results=current.raw_results,
    )
