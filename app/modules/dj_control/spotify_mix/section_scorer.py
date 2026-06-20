"""Score section pairs for local Spotify-style transition planning."""

from __future__ import annotations

from typing import Any

from app.modules.dj_control.spotify_mix.camelot_distance import camelot_distance


def score_section_pair(
    a_section: dict[str, Any],
    b_section: dict[str, Any],
    *,
    song_a_bpm: float,
    song_b_bpm: float,
    song_a_key: str,
    song_b_key: str,
) -> dict[str, Any]:
    """Return a 100-point compatibility score and an EQ-band strategy."""
    breakdown: dict[str, Any] = {}
    issues: list[str] = []
    total = 0.0

    base_score = min(20.0, (_float(a_section.get("priority"), 50.0) + _float(b_section.get("priority"), 50.0)) / 10.0)
    breakdown["base_priority"] = round(base_score, 1)
    total += base_score

    a_bpm = _float(a_section.get("tempo"), song_a_bpm)
    b_bpm = _float(b_section.get("tempo"), song_b_bpm)
    bpm_ratio = max(a_bpm, b_bpm) / min(a_bpm, b_bpm) if a_bpm > 0 and b_bpm > 0 else 1.0
    if bpm_ratio <= 1.03:
        bpm_score = 20.0
    elif bpm_ratio <= 1.06:
        bpm_score = 16.0
    elif bpm_ratio <= 1.10:
        bpm_score = 12.0
    elif bpm_ratio <= 1.15:
        bpm_score = 8.0
        issues.append(f"BPM differs by {(bpm_ratio - 1.0) * 100.0:.0f}%")
    elif bpm_ratio <= 1.20:
        bpm_score = 4.0
        issues.append(f"BPM differs by {(bpm_ratio - 1.0) * 100.0:.0f}%, use masking")
    else:
        bpm_score = 0.0
        issues.append(f"BPM differs by {(bpm_ratio - 1.0) * 100.0:.0f}%, rough")
    breakdown["bpm"] = bpm_score
    breakdown["bpm_ratio"] = round(bpm_ratio, 3)
    total += bpm_score

    try:
        key_dist = camelot_distance(song_a_key or "8A", song_b_key or "8A")
    except ValueError:
        key_dist = 3
        issues.append("invalid Camelot key")
    if key_dist == 0:
        key_score = 15.0
    elif key_dist == 1:
        key_score = 13.0
    elif key_dist == 2:
        key_score = 9.0
    elif key_dist == 3:
        key_score = 5.0
        issues.append("moderate key distance")
    else:
        key_score = max(0.0, 15.0 - key_dist * 3.0)
        issues.append(f"key distance {key_dist}")
    breakdown["key"] = round(key_score, 1)
    breakdown["key_distance"] = key_dist
    total += key_score

    loudness_delta = abs(_float(a_section.get("loudness_end"), -10.0) - _float(b_section.get("loudness_start"), -10.0))
    if loudness_delta < 2.0:
        loudness_score = 10.0
    elif loudness_delta < 4.0:
        loudness_score = 7.0
    elif loudness_delta < 6.0:
        loudness_score = 4.0
        issues.append(f"loudness delta {loudness_delta:.1f} dB")
    else:
        loudness_score = 2.0
        issues.append(f"large loudness delta {loudness_delta:.1f} dB")
    breakdown["loudness"] = loudness_score
    breakdown["loudness_delta_db"] = round(loudness_delta, 1)
    total += loudness_score

    a_vocal = _float(a_section.get("vocal_density_end"), 0.35)
    b_vocal = _float(b_section.get("vocal_density_start"), 0.35)
    both_vocal = min(a_vocal, b_vocal)
    one_sided_vocal = max(a_vocal, b_vocal) >= 0.55 and both_vocal < 0.25
    hard_vocal_conflict = a_vocal >= 0.60 and b_vocal >= 0.60
    medium_vocal_conflict = both_vocal >= 0.35
    if hard_vocal_conflict:
        vocal_score = -35.0
        issues.append("hard double vocal overlap")
    elif medium_vocal_conflict:
        vocal_score = -16.0
        issues.append("double vocal overlap")
    elif one_sided_vocal:
        vocal_score = 15.0
    elif a_vocal <= 0.3 and b_vocal <= 0.3:
        vocal_score = 15.0
    elif both_vocal <= 0.25:
        vocal_score = 10.0
    else:
        vocal_score = 2.0
        issues.append("light double vocal overlap")
    breakdown["vocal"] = vocal_score
    breakdown["a_end_vocal"] = round(a_vocal, 2)
    breakdown["b_start_vocal"] = round(b_vocal, 2)
    breakdown["both_vocal"] = round(both_vocal, 2)
    breakdown["one_sided_vocal_allowed"] = one_sided_vocal
    breakdown["hard_vocal_conflict"] = hard_vocal_conflict
    total += vocal_score

    a_low = _float(a_section.get("low_band_energy"), 0.5)
    b_low = _float(b_section.get("low_band_energy"), 0.5)
    low_sum = a_low + b_low
    if low_sum > 1.4:
        low_score = 2.0
        issues.append("heavy low-band overlap")
    elif low_sum > 1.1:
        low_score = 6.0
    else:
        low_score = 10.0
    breakdown["low_band"] = low_score
    breakdown["a_low_energy"] = round(a_low, 2)
    breakdown["b_low_energy"] = round(b_low, 2)
    total += low_score

    completeness = 0.0
    if a_section.get("ends_at_downbeat"):
        completeness += 5.0
    if b_section.get("starts_at_downbeat"):
        completeness += 5.0
    breakdown["completeness"] = completeness
    total += completeness

    strategy = choose_strategy(
        bpm_ratio=bpm_ratio,
        key_dist=key_dist,
        a_low=a_low,
        b_low=b_low,
        a_vocal=a_vocal,
        b_vocal=b_vocal,
        energy_delta=abs(_float(a_section.get("energy"), 0.5) - _float(b_section.get("energy"), 0.5)),
        total_score=total,
    )
    return {
        "total": round(total, 1),
        "breakdown": breakdown,
        "strategy": strategy,
        "issues": issues,
    }


def choose_strategy(
    *,
    bpm_ratio: float,
    key_dist: int,
    a_low: float,
    b_low: float,
    a_vocal: float,
    b_vocal: float,
    energy_delta: float,
    total_score: float,
) -> str:
    if bpm_ratio > 1.20 or key_dist >= 5:
        return "soft_bass_swap"
    if min(a_vocal, b_vocal) >= 0.35:
        return "vocal_safe"
    if bpm_ratio > 1.10 or key_dist >= 3:
        return "soft_bass_swap"
    if a_low + b_low > 1.4:
        return "hard_bass_swap"
    if a_low + b_low > 1.1:
        return "soft_bass_swap"
    if energy_delta >= 0.22 and total_score >= 65:
        return "overlap"
    if total_score >= 80:
        return "smooth_blend"
    if total_score >= 60:
        return "soft_bass_swap"
    return "soft_bass_swap"


def quality_tier(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 60:
        return "ok"
    if score >= 45:
        return "rough"
    return "poor"


def recommend_transition_duration_beats(strategy: str, *, bpm_ratio: float, key_dist: int) -> int:
    beats = {
        "hard_bass_swap": 10,
        "soft_bass_swap": 12,
        "filter_sweep": 10,
        "vocal_safe": 12,
        "smooth_blend": 14,
        "overlap": 16,
    }.get(strategy, 12)
    if bpm_ratio > 1.15 or key_dist >= 4:
        beats = min(beats, 8)
    return beats


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
