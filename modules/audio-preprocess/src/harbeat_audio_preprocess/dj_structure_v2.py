"""Planner-ready DJ structure analysis for library songs.

The result is stored under ``LibrarySong.music_features["dj_structure_v2"]``.
It deliberately reuses persisted beat/downbeat/phrase metadata first, then
loads audio only to score local handoff quality around candidate boundaries.
"""
from __future__ import annotations

from datetime import datetime
import math
import os
from typing import Any

import numpy as np


VERSION = "dj_structure_v2"


class DJStructureAnalysisError(RuntimeError):
    """Raised when DJ structure analysis cannot be produced."""


def apply_dj_structure_analysis(song: Any, *, force: bool = False) -> dict[str, Any]:
    """Compute and persist ``music_features.dj_structure_v2`` on ``song``.

    Returns the computed or existing structure payload.  The caller owns the DB
    session and commit.
    """
    music_features = dict(getattr(song, "music_features", {}) or {})
    existing = music_features.get(VERSION)
    if isinstance(existing, dict) and existing.get("version") == VERSION and not force:
        return existing

    result = analyze_song_dj_structure(song)
    music_features[VERSION] = result
    song.music_features = music_features
    return result


def analyze_song_dj_structure(song: Any) -> dict[str, Any]:
    path = str(getattr(song, "source_path", "") or "")
    if not path or not os.path.isfile(path):
        raise DJStructureAnalysisError(f"audio file not found: {path}")

    try:
        import librosa
    except Exception as exc:  # pragma: no cover - deployment dependency
        raise DJStructureAnalysisError(f"librosa unavailable: {exc}") from exc

    audio, sr = librosa.load(path, sr=22050, mono=True)
    duration = float(getattr(song, "duration", None) or (len(audio) / float(sr) if sr else 0.0))
    beats = _float_list(getattr(song, "beat_points", None))
    if not beats:
        beats = _detect_beats(audio, sr, librosa)
    downbeats = _float_list(getattr(song, "downbeats", None))
    bars = downbeats if downbeats else beats[::4]
    phrase_boundaries = _phrase_boundaries_from_song(song, beats)
    phrase_change_boundaries = _phrase_change_boundaries(audio, sr, phrase_boundaries or bars, librosa)

    candidate_points = _combined_candidate_points(
        phrase_change_boundaries,
        phrase_boundaries,
        bars,
        beats,
        limit=64,
    )

    exit_candidates = _track1_exit_candidates(
        audio,
        sr,
        candidate_points=candidate_points,
        duration=duration,
        librosa=librosa,
    )
    entry_candidates = _track2_entry_candidates(
        audio,
        sr,
        candidate_points=candidate_points,
        duration=duration,
        librosa=librosa,
    )

    return _json_safe({
        "version": VERSION,
        "source": "harbeat_dj_structure_analysis_v2",
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "audio_path": path,
        "duration_sec": round(duration, 3),
        "beat_boundaries": _round_list(beats),
        "bar_boundaries": _round_list(bars),
        "phrase_boundaries": _round_list(phrase_boundaries),
        "phrase_change_boundaries": _round_list(phrase_change_boundaries),
        "track1_exit_candidates": exit_candidates,
        "track2_entry_candidates": entry_candidates,
        "limits": {
            "candidate_scan_limit": 64,
            "stored_exit_candidates": len(exit_candidates),
            "stored_entry_candidates": len(entry_candidates),
            "candidate_feature_source": "dj_structure_precomputed_window_v2",
        },
    })


def _detect_beats(audio: np.ndarray, sr: int, librosa: Any) -> list[float]:
    try:
        _, frames = librosa.beat.beat_track(y=audio, sr=sr)
        return [float(t) for t in librosa.frames_to_time(frames, sr=sr)]
    except Exception:
        return []


def _phrase_boundaries_from_song(song: Any, beats: list[float]) -> list[float]:
    phrases = getattr(song, "phrase_map", None) or []
    out: list[float] = []
    if isinstance(phrases, list):
        for item in phrases:
            if not isinstance(item, dict):
                continue
            t = _float(item.get("start", item.get("start_sec")), None)
            if t is not None:
                out.append(t)
    if out:
        return sorted(set(round(float(t), 3) for t in out))
    return [float(t) for t in beats[::32]]


def _phrase_change_boundaries(audio: np.ndarray, sr: int, anchors: list[float], librosa: Any) -> list[float]:
    duration = len(audio) / float(sr)
    if not anchors:
        return []
    scored: list[tuple[float, float]] = []
    for anchor in _limit_points(anchors, 64):
        if anchor < 4.0 or anchor > duration - 4.0:
            continue
        best_t = float(anchor)
        best_score = -1.0
        for t in (anchor - 1.0, anchor - 0.5, anchor, anchor + 0.5, anchor + 1.0):
            if t < 3.0 or t > duration - 3.0:
                continue
            score = _structure_change_score(audio, sr, t, librosa, window_sec=4.0)
            if score > best_score:
                best_score = score
                best_t = float(t)
        scored.append((best_t, best_score))
    return [t for t, _score in sorted(scored, key=lambda item: item[0])]


def _track1_exit_candidates(
    audio: np.ndarray,
    sr: int,
    *,
    candidate_points: list[float],
    duration: float,
    librosa: Any,
) -> list[dict[str, Any]]:
    # Fast-cut may be requested shortly after playback starts or near the end.
    # Precompute the same boundary features across the full usable timeline so
    # a 10-15 second live window does not fall back to unlabeled downbeats.
    start = 4.0
    end = max(start, duration - 2.0)
    points = [t for t in _limit_points(candidate_points, 64) if start <= t <= min(end, duration - 2.0)]
    candidates: list[dict[str, Any]] = []
    for t in points:
        vocal_sparsity = _local_vocal_sparsity(audio, sr, t, librosa, align="end")
        drum_stability = _local_drum_stability(audio, sr, t, librosa, align="end")
        melodic_presence = _melodic_presence(audio, sr, t, librosa, align="end")
        fullness = _fullness(audio, sr, t, librosa, align="end")
        handoff = _handoff_readiness(audio, sr, t, librosa)
        tail_score, tail_rms = _tail_energy(audio, sr, t)
        change = _structure_change_score(audio, sr, t, librosa, window_sec=4.0)
        score = (
            0.16 * vocal_sparsity
            + 0.20 * drum_stability
            + 0.22 * handoff
            + 0.10 * melodic_presence
            + 0.20 * tail_score
            + 0.12 * change
            - 0.10 * (1.0 - vocal_sparsity)
        )
        candidates.append({
            "time": round(float(t), 3),
            "type": "track1_exit_candidate",
            "source": VERSION,
            "score": round(float(score), 4),
            "structure_change_score": round(change, 4),
            "local_rms": round(tail_rms, 6),
            "vocal_sparsity": round(vocal_sparsity, 4),
            "drum_strength": round(drum_stability, 4),
            "drum_stability": round(drum_stability, 4),
            "immediate_punch": round(_clip01(fullness), 4),
            "melodic_presence": round(melodic_presence, 4),
            "fullness": round(fullness, 4),
            "fullness_score": round(fullness, 4),
            "handoff_readiness": round(handoff, 4),
            "tail_energy_score": round(tail_score, 4),
            "tail_rms": round(tail_rms, 6),
            "audio_feature_source": "dj_structure_precomputed_window_v2",
            "reason": "phrase/bar boundary with local sparse vocal, stable drum, and usable tail energy",
        })
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:64]


def _track2_entry_candidates(
    audio: np.ndarray,
    sr: int,
    *,
    candidate_points: list[float],
    duration: float,
    librosa: Any,
) -> list[dict[str, Any]]:
    upper = min(90.0, duration * 0.50) if duration > 0 else 90.0
    points = [t for t in _limit_points(candidate_points, 64) if 2.0 <= t <= upper]
    candidates: list[dict[str, Any]] = []
    for t in points:
        entry_rms = _rms(_window(audio, sr, t, 6.0, align="start"))
        drum = _entry_drum_strength(audio, sr, t, librosa)
        punch = _immediate_entry_punch(audio, sr, t, librosa)
        vocal_sparsity = _local_vocal_sparsity(audio, sr, t, librosa, align="start")
        melodic = _melodic_presence(audio, sr, t, librosa, align="start")
        fullness = _fullness(audio, sr, t, librosa, align="start")
        ratios = _band_ratios(_window(audio, sr, t, 6.0, align="start"), sr, librosa)
        score = (
            0.22 * drum
            + 0.22 * punch
            + 0.28 * vocal_sparsity
            + 0.14 * melodic
            + 0.14 * fullness
        )
        candidates.append({
            "time": round(float(t), 3),
            "type": "track2_entry_candidate",
            "source": VERSION,
            "score": round(float(score), 4),
            "entry_score": round(float(score), 4),
            "local_rms": round(entry_rms, 6),
            "entry_rms": round(entry_rms, 6),
            "drum_strength": round(drum, 4),
            "drum_entry_strength": round(drum, 4),
            "immediate_punch": round(punch, 4),
            "immediate_entry_punch": round(punch, 4),
            "vocal_sparsity": round(vocal_sparsity, 4),
            "vocal_entry_sparsity": round(vocal_sparsity, 4),
            "melodic_presence": round(melodic, 4),
            "fullness": round(fullness, 4),
            "fullness_score": round(fullness, 4),
            "handoff_readiness": round(_clip01(0.45 * drum + 0.35 * punch + 0.20 * fullness), 4),
            "low_ratio": round(ratios["low_ratio"], 4),
            "mid_ratio": round(ratios["mid_ratio"], 4),
            "high_ratio": round(ratios["high_ratio"], 4),
            "candidate_scan_mode": "dj_structure_v2_boundaries",
            "audio_feature_source": "dj_structure_precomputed_window_v2",
            "reason": "early phrase/bar boundary with drum punch, sparse vocal, and usable fullness",
        })
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:64]


def _structure_change_score(audio: np.ndarray, sr: int, center: float, librosa: Any, *, window_sec: float) -> float:
    before = _window(audio, sr, center, window_sec, align="end")
    after = _window(audio, sr, center, window_sec, align="start")
    if len(before) < 1024 or len(after) < 1024:
        return 0.0
    before_rms = _rms(before)
    after_rms = _rms(after)
    energy_change = abs(math.log((after_rms + 1e-8) / (before_rms + 1e-8)))
    energy_score = _clip01(energy_change / 0.8)
    try:
        before_stft = np.abs(librosa.stft(before))
        after_stft = np.abs(librosa.stft(after))
        band_score = _band_distance(before_stft, after_stft, sr, librosa)
        before_onset = librosa.onset.onset_strength(y=librosa.effects.percussive(before), sr=sr)
        after_onset = librosa.onset.onset_strength(y=librosa.effects.percussive(after), sr=sr)
        onset_score = _clip01(
            abs(_mean(after_onset) - _mean(before_onset)) / max(_mean(before_onset), _mean(after_onset), 1e-8)
        )
    except Exception:
        band_score = 0.0
        onset_score = 0.0
    return _clip01(0.34 * energy_score + 0.40 * band_score + 0.26 * onset_score)


def _local_vocal_sparsity(audio: np.ndarray, sr: int, center: float, librosa: Any, *, align: str) -> float:
    segment = _window(audio, sr, center, 6.0, align=align)
    if len(segment) < 1024:
        return 0.0
    ratios = _band_ratios(segment, sr, librosa)
    return _clip01(1.0 - ratios["mid_ratio"])


def _local_drum_stability(audio: np.ndarray, sr: int, center: float, librosa: Any, *, align: str) -> float:
    segment = _window(audio, sr, center, 6.0, align=align)
    if len(segment) < 1024:
        return 0.0
    try:
        onset = librosa.onset.onset_strength(y=segment, sr=sr)
    except Exception:
        return 0.0
    if onset.size < 3:
        return 0.0
    mean = _mean(onset)
    if mean <= 1e-8:
        return 0.0
    consistency = _clip01(1.0 - float(np.std(onset)) / max(mean * 2.5, 1e-8))
    strength = _clip01(mean / 6.0)
    return _clip01(0.55 * consistency + 0.45 * strength)


def _melodic_presence(audio: np.ndarray, sr: int, center: float, librosa: Any, *, align: str) -> float:
    segment = _window(audio, sr, center, 6.0, align=align)
    if len(segment) < 1024:
        return 0.0
    ratios = _band_ratios(segment, sr, librosa)
    return _clip01(0.65 * _clip01(ratios["mid_ratio"] / 0.45) + 0.35 * _clip01(ratios["high_ratio"] / 0.20))


def _fullness(audio: np.ndarray, sr: int, center: float, librosa: Any, *, align: str) -> float:
    segment = _window(audio, sr, center, 6.0, align=align)
    if len(segment) < 1024:
        return 0.0
    ratios = _band_ratios(segment, sr, librosa)
    rms_score = _clip01(_rms(segment) / 0.22)
    return _clip01(0.45 * rms_score + 0.35 * _clip01(ratios["mid_ratio"] / 0.45) + 0.20 * _clip01(ratios["high_ratio"] / 0.18))


def _handoff_readiness(audio: np.ndarray, sr: int, center: float, librosa: Any) -> float:
    before = _window(audio, sr, center - 1.5, 3.0, align="center")
    after = _window(audio, sr, center + 1.5, 3.0, align="center")
    before_rms = _rms(before)
    after_rms = _rms(after)
    if before_rms < 1e-8 and after_rms < 1e-8:
        return 0.0
    continuity = _clip01(1.0 - abs(after_rms - before_rms) / max(before_rms, after_rms, 1e-10))
    tail_hold = _clip01(after_rms / max(before_rms, 1e-10))
    tail_presence = _clip01(after_rms / 0.18)
    drums = _local_drum_stability(audio, sr, center, librosa, align="center")
    return _clip01(0.40 * continuity + 0.30 * tail_hold + 0.15 * tail_presence + 0.15 * drums)


def _tail_energy(audio: np.ndarray, sr: int, center: float) -> tuple[float, float]:
    tail = _window(audio, sr, center, 6.0, align="end")
    tail_rms = _rms(tail)
    return _clip01(tail_rms / 0.22), tail_rms


def _entry_drum_strength(audio: np.ndarray, sr: int, start: float, librosa: Any) -> float:
    segment = _window(audio, sr, start, 6.0, align="start")
    early = _window(audio, sr, start, 1.0, align="start")
    if len(segment) < 1024:
        return 0.0
    try:
        onset = librosa.onset.onset_strength(y=segment, sr=sr)
        early_onset = librosa.onset.onset_strength(y=early if len(early) else segment, sr=sr)
    except Exception:
        return 0.0
    onset_score = _clip01(_mean(onset) / 6.0)
    early_score = _clip01(_mean(early_onset) / 6.5)
    attack_score = _clip01(float(np.max(early_onset)) / 12.0) if early_onset.size else 0.0
    ratios = _band_ratios(segment, sr, librosa)
    return _clip01(0.25 * onset_score + 0.25 * early_score + 0.25 * attack_score + 0.25 * _clip01(ratios["low_ratio"] / 0.40))


def _immediate_entry_punch(audio: np.ndarray, sr: int, start: float, librosa: Any) -> float:
    segment = _window(audio, sr, start, 0.8, align="start")
    if len(segment) < 512:
        return 0.0
    try:
        onset = librosa.onset.onset_strength(y=segment, sr=sr)
    except Exception:
        return 0.0
    peak = _clip01(float(np.max(onset)) / 14.0) if onset.size else 0.0
    mean = _clip01(_mean(onset) / 7.0)
    ratios = _band_ratios(segment, sr, librosa)
    return _clip01(0.40 * peak + 0.25 * mean + 0.35 * _clip01(ratios["low_ratio"] / 0.42))


def _band_ratios(segment: np.ndarray, sr: int, librosa: Any) -> dict[str, float]:
    if len(segment) < 512:
        return {"low_ratio": 0.0, "mid_ratio": 0.0, "high_ratio": 0.0}
    try:
        stft = np.abs(librosa.stft(segment))
        freqs = librosa.fft_frequencies(sr=sr)
        total = float(np.sum(stft)) + 1e-10
        low = float(np.sum(stft[freqs < 250, :]) / total)
        mid = float(np.sum(stft[(freqs >= 250) & (freqs < 4000), :]) / total)
        high = float(np.sum(stft[freqs >= 4000, :]) / total)
        return {"low_ratio": _clip01(low), "mid_ratio": _clip01(mid), "high_ratio": _clip01(high)}
    except Exception:
        return {"low_ratio": 0.0, "mid_ratio": 0.0, "high_ratio": 0.0}


def _band_distance(before_stft: np.ndarray, after_stft: np.ndarray, sr: int, librosa: Any) -> float:
    freqs = librosa.fft_frequencies(sr=sr)
    bands = [
        freqs < 150,
        (freqs >= 150) & (freqs < 500),
        (freqs >= 500) & (freqs < 2500),
        (freqs >= 2500) & (freqs < 6000),
        freqs >= 6000,
    ]

    def profile(stft: np.ndarray) -> np.ndarray:
        total = float(np.sum(stft)) + 1e-10
        return np.asarray([float(np.sum(stft[band, :]) / total) for band in bands])

    return _clip01(float(np.sum(np.abs(profile(after_stft) - profile(before_stft)))) / 0.7)


def _window(audio: np.ndarray, sr: int, center: float, duration: float, *, align: str) -> np.ndarray:
    if align == "end":
        start = center - duration
        end = center
    elif align == "start":
        start = center
        end = center + duration
    else:
        half = duration * 0.5
        start = center - half
        end = center + half
    s0 = max(0, int(round(start * sr)))
    s1 = min(len(audio), int(round(end * sr)))
    if s1 <= s0:
        return np.asarray([], dtype=np.float32)
    return np.asarray(audio[s0:s1], dtype=np.float32)


def _rms(audio: np.ndarray) -> float:
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))


def _mean(values: np.ndarray) -> float:
    return float(np.mean(values)) if getattr(values, "size", 0) else 0.0


def _float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except (TypeError, ValueError):
        return default


def _float_list(values: Any) -> list[float]:
    if not isinstance(values, list):
        return []
    out: list[float] = []
    for value in values:
        parsed = _float(value, None)
        if parsed is not None:
            out.append(parsed)
    return sorted(set(round(float(v), 3) for v in out))


def _limit_points(points: list[float], limit: int) -> list[float]:
    points = sorted(set(float(p) for p in points))
    if len(points) <= limit:
        return points
    indices = np.linspace(0, len(points) - 1, limit, dtype=int)
    return [points[int(i)] for i in indices]


def _combined_candidate_points(*groups: list[float], limit: int) -> list[float]:
    points: list[float] = []
    seen: set[float] = set()
    for group in groups:
        for value in group:
            rounded = round(float(value), 3)
            if rounded in seen:
                continue
            seen.add(rounded)
            points.append(rounded)
    return _limit_points(sorted(points), limit)


def _round_list(values: list[float]) -> list[float]:
    return [round(float(v), 3) for v in values]


def _clip01(value: Any) -> float:
    parsed = _float(value, 0.0)
    return float(max(0.0, min(1.0, parsed or 0.0)))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    return value
