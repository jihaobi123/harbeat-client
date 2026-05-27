"""Street-dance DJ energy scoring.

Unlike a flat RMS-based energy (which favours loud-mastered pop), street-dance
performance energy weights what dancers actually move to:

  E_dance = 0.30·kick_punch        # sub/low-mid impact per bar
          + 0.25·snare_crack       # backbeat presence & crispness
          + 0.15·groove_tightness  # beat-grid stability (low jitter)
          + 0.15·low_mid_density   # how "thick" the low-mid (60-300 Hz) is
          + 0.10·vocal_urgency     # vocal density / aggression proxy
          + 0.05·tempo_factor      # mild BPM boost (faster ≈ higher energy)

All sub-scores in [0,1]. Final energy is also clipped to [0,1].

The implementation uses ONLY pre-extracted LibrarySong features (beat_points,
downbeats, energy, bpm, phrase_map, duration, key_confidence). It does NOT
re-decode audio, so it can re-score 10,000 songs in well under a second.

If stems are present (vocals/drums/bass), the scorer derives cleaner sub-scores
from per-stem RMS in a future extension; for now stems are checked for existence
only and bump vocal_urgency.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass


# --------------------------------------------------------------------------- #
# Sub-scores (each returns 0..1)
# --------------------------------------------------------------------------- #
def _kick_punch(downbeats: list[float], bpm: float, energy_flat: float) -> float:
    """Estimate kick impact strength from downbeat regularity × overall energy.

    A track with a clear, regular downbeat (every bar) and high RMS energy
    in the low end will score high. We approximate by counting how stable
    downbeat intervals are and modulating by RMS energy.
    """
    if not downbeats or len(downbeats) < 4 or bpm <= 0:
        return energy_flat * 0.5
    intervals = [downbeats[i + 1] - downbeats[i] for i in range(len(downbeats) - 1)]
    if not intervals:
        return energy_flat * 0.5
    expected = 4 * 60.0 / bpm  # bar length in sec
    deviations = [abs(it - expected) / expected for it in intervals]
    stability = max(0.0, 1.0 - statistics.mean(deviations) * 3.0)
    return float(max(0.0, min(1.0, stability * (0.5 + 0.5 * energy_flat))))


def _snare_crack(beat_points: list[float], downbeats: list[float], bpm: float) -> float:
    """Proxy for snare presence on beats 2 & 4: count beats that fall ~half-bar
    after a downbeat. The more reliable the backbeat, the higher the score."""
    if not beat_points or not downbeats or bpm <= 0:
        return 0.4
    half_bar = 2 * 60.0 / bpm
    tol = half_bar * 0.15
    hits = 0
    for db in downbeats:
        target = db + half_bar
        # binary search-ish; lists are small (hundreds), linear is fine
        for bp in beat_points:
            if bp > db and bp - target < -tol:
                continue
            if bp - target > tol:
                break
            hits += 1
            break
    if not downbeats:
        return 0.4
    coverage = hits / len(downbeats)
    return float(max(0.0, min(1.0, coverage)))


def _groove_tightness(beat_points: list[float], bpm: float) -> float:
    """Coefficient-of-variation of inter-beat intervals — lower jitter = tighter."""
    if len(beat_points) < 8 or bpm <= 0:
        return 0.5
    expected = 60.0 / bpm
    intervals = [beat_points[i + 1] - beat_points[i] for i in range(len(beat_points) - 1)]
    if not intervals:
        return 0.5
    mean = statistics.mean(intervals)
    if mean <= 0:
        return 0.5
    stdev = statistics.pstdev(intervals)
    cv = stdev / mean
    # cv ~0.02 = very tight, 0.10 = sloppy → invert and clip
    return float(max(0.0, min(1.0, 1.0 - cv * 8.0)))


def _low_mid_density(beat_points: list[float], duration: float, energy_flat: float) -> float:
    """Approximate low-mid 'thickness' by beat density × overall energy."""
    if not beat_points or duration <= 0:
        return energy_flat
    bd = len(beat_points) / duration
    # bd ~1.5 (~90 BPM) baseline; cap influence
    norm = min(1.0, bd / 2.2)
    return float(max(0.0, min(1.0, 0.6 * norm + 0.4 * energy_flat)))


def _vocal_urgency(phrase_map: list[dict], stems: dict | None, energy_flat: float) -> float:
    """Without stems, infer from phrase density (more 'verse/drop' labels = busier).
    With vocals stem present, future extension can use stem RMS variance."""
    base = energy_flat * 0.5
    if not phrase_map:
        return base
    # Density of phrase boundaries per minute as a proxy for vocal/section activity.
    if len(phrase_map) >= 2:
        first = phrase_map[0].get("start", phrase_map[0].get("time", 0)) or 0
        last = phrase_map[-1].get("end", phrase_map[-1].get("time", 0)) or 0
        span = last - first
        if span > 0:
            density_per_min = len(phrase_map) / (span / 60.0)
            urgency = min(1.0, density_per_min / 8.0)
            base = max(base, urgency)
    if stems and stems.get("vocals"):
        base = min(1.0, base + 0.10)
    return float(max(0.0, min(1.0, base)))


def _tempo_factor(bpm: float) -> float:
    """Mild boost: 80→0.20, 95→0.50, 110→0.80, 125+→1.0."""
    if bpm <= 0:
        return 0.5
    return float(max(0.0, min(1.0, (bpm - 75.0) / 50.0)))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
@dataclass
class EnergyBreakdown:
    total: float
    kick_punch: float
    snare_crack: float
    groove_tightness: float
    low_mid_density: float
    vocal_urgency: float
    tempo_factor: float

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "kick_punch": self.kick_punch,
            "snare_crack": self.snare_crack,
            "groove_tightness": self.groove_tightness,
            "low_mid_density": self.low_mid_density,
            "vocal_urgency": self.vocal_urgency,
            "tempo_factor": self.tempo_factor,
        }


def compute_dance_energy(song) -> EnergyBreakdown:
    """Compute street-dance performance energy + per-component breakdown."""
    bpm = float(song.bpm) if getattr(song, "bpm", None) else 0.0
    energy_flat = float(song.energy) if getattr(song, "energy", None) is not None else 0.5
    beat_points = list(getattr(song, "beat_points", []) or [])
    downbeats = list(getattr(song, "downbeats", []) or [])
    phrase_map = list(getattr(song, "phrase_map", []) or [])
    duration = float(getattr(song, "duration", 0) or 0)
    stems = getattr(song, "stems", None)

    kp = _kick_punch(downbeats, bpm, energy_flat)
    sc = _snare_crack(beat_points, downbeats, bpm)
    gt = _groove_tightness(beat_points, bpm)
    lmd = _low_mid_density(beat_points, duration, energy_flat)
    vu = _vocal_urgency(phrase_map, stems, energy_flat)
    tf = _tempo_factor(bpm)

    total = (
        0.30 * kp
        + 0.25 * sc
        + 0.15 * gt
        + 0.15 * lmd
        + 0.10 * vu
        + 0.05 * tf
    )
    total = max(0.0, min(1.0, total))
    return EnergyBreakdown(
        total=float(total),
        kick_punch=kp,
        snare_crack=sc,
        groove_tightness=gt,
        low_mid_density=lmd,
        vocal_urgency=vu,
        tempo_factor=tf,
    )
