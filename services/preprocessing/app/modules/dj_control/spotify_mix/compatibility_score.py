"""Spotify Mix compatibility scoring algorithm.

Scores how well two tracks pair for a transition based on BPM, key,
energy, and loudness compatibility.
"""
from __future__ import annotations

from typing import Any, Dict

from .camelot_distance import camelot_distance


def calculate_spotify_compatibility(
    prev_song: Dict[str, Any],
    next_song: Dict[str, Any],
) -> Dict[str, Any]:
    """Calculate Spotify Mix compatibility score between two tracks.

    Scoring dimensions:
        1. BPM difference (40 points)
        2. Key compatibility (30 points)
        3. Energy change (20 points)
        4. Loudness match (10 points)

    Args:
        prev_song: Current track features (bpm, camelot_key, energy, loudness).
        next_song: Next track features.

    Returns:
        {
            'score': 0-100,
            'bpm_score': 0-40,
            'key_score': 0-30,
            'energy_score': 0-20,
            'loudness_score': 0-10,
            'issues': [...]
        }
    """
    score = 100.0
    issues: list[str] = []
    breakdown: dict[str, float] = {}

    # 1. BPM scoring
    bpm1 = float(prev_song.get('bpm') or 120)
    bpm2 = float(next_song.get('bpm') or 120)
    if bpm1 <= 0 or bpm2 <= 0:
        bpm1 = bpm1 or 120
        bpm2 = bpm2 or 120
    bpm_ratio = max(bpm1, bpm2) / min(bpm1, bpm2)

    if bpm_ratio <= 1.03:  # ±3% perfect
        bpm_score = 40.0
    elif bpm_ratio <= 1.05:  # ±5% excellent
        bpm_score = 35.0
    elif bpm_ratio <= 1.10:  # ±10% good
        bpm_score = 25.0
        issues.append(f"BPM diff {(bpm_ratio - 1) * 100:.1f}%")
    elif bpm_ratio <= 1.15:  # ±15% acceptable
        bpm_score = 15.0
        issues.append(f"BPM diff {(bpm_ratio - 1) * 100:.1f}%, time stretch needed")
    else:  # >15% poor
        bpm_score = max(0.0, 40 - (bpm_ratio - 1.15) * 100)
        issues.append(f"BPM diff {(bpm_ratio - 1) * 100:.1f}%, transition difficult")

    breakdown['bpm_score'] = bpm_score
    score -= (40 - bpm_score)

    severe_bpm_penalty = 0.0
    if bpm_ratio > 1.20:
        severe_bpm_penalty = min(20.0, (bpm_ratio - 1.20) * 30.0)
        score -= severe_bpm_penalty

    # 2. Key compatibility scoring
    key1 = prev_song.get('camelot_key') or ''
    key2 = next_song.get('camelot_key') or ''
    key_dist: int | None = None

    if key1 and key2:
        try:
            key_dist = camelot_distance(key1, key2)
            if key_dist == 0:
                key_score = 30.0
            elif key_dist == 1:
                key_score = 25.0
            elif key_dist == 2:
                key_score = 15.0
                issues.append(f"Key not very compatible ({key1} → {key2})")
            else:
                key_score = max(0.0, 30 - key_dist * 8)
                issues.append(f"Key conflict ({key1} → {key2})")
        except ValueError:
            key_score = 15.0
            issues.append("Invalid key info")
    else:
        key_score = 15.0
        issues.append("Missing key info")

    breakdown['key_score'] = key_score
    score -= (30 - key_score)

    # 3. Energy change scoring
    energy1 = float(prev_song.get('energy') or 0.5)
    energy2 = float(next_song.get('energy') or 0.5)
    energy_delta = abs(energy2 - energy1)

    if energy_delta < 0.15:
        energy_score = 20.0
    elif energy_delta < 0.30:
        energy_score = 15.0
    elif energy_delta < 0.50:
        energy_score = 10.0
        issues.append(f"Energy delta large (Δ{energy_delta:.2f})")
    else:
        energy_score = 5.0
        issues.append(f"Energy jump (Δ{energy_delta:.2f})")

    breakdown['energy_score'] = energy_score
    score -= (20 - energy_score)

    # 4. Loudness match scoring
    loudness1 = float(prev_song.get('loudness') if prev_song.get('loudness') is not None else -8)
    loudness2 = float(next_song.get('loudness') if next_song.get('loudness') is not None else -8)
    loudness_delta = abs(loudness2 - loudness1)

    if loudness_delta < 2:
        loudness_score = 10.0
    elif loudness_delta < 4:
        loudness_score = 7.0
    elif loudness_delta < 6:
        loudness_score = 4.0
    else:
        loudness_score = 2.0
        issues.append(f"Loudness diff large ({loudness_delta:.1f} dB)")

    breakdown['loudness_score'] = loudness_score
    score -= (10 - loudness_score)

    return {
        'score': max(0.0, min(100.0, score)),
        **breakdown,
        'issues': issues,
        'bpm_ratio': bpm_ratio,
        'severe_bpm_penalty': severe_bpm_penalty,
        'key_distance': key_dist,
        'energy_delta': energy_delta,
    }
