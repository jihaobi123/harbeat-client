"""Candidate scoring for mini set planning."""

from __future__ import annotations

from .drums import drum_overlap_score
from .key_compatibility import harmonic_compatibility_score
from .models import CandidateScore, PairAnalysis, TrackProfile, TransitionConfig


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _same_style(left: TrackProfile, right: TrackProfile) -> bool:
    return left.style.strip().lower() == right.style.strip().lower()


def score_transition_candidate(
    current: TrackProfile,
    candidate: TrackProfile,
    config: TransitionConfig | None = None,
    pair_analysis: PairAnalysis | None = None,
) -> CandidateScore:
    """Score how well candidate can follow current in a mini set."""

    config = config or TransitionConfig()
    pair_analysis = pair_analysis or PairAnalysis()

    bpm_delta = candidate.bpm - current.bpm
    bpm_abs_delta = abs(bpm_delta)
    bpm_proximity = _clamp01(1.0 - (bpm_abs_delta / config.bpm_score_window))

    if bpm_delta > 0:
        bpm_trend = 1.0 if bpm_delta <= config.preferred_bpm_diff else 0.80
    elif bpm_delta == 0:
        bpm_trend = 0.75
    else:
        bpm_trend = 0.0

    drum_overlap = (
        pair_analysis.drum_overlap
        if pair_analysis.drum_overlap is not None
        else drum_overlap_score(current.drum_profile, candidate.drum_profile)
    )
    drum_overlap = _clamp01(drum_overlap)

    if pair_analysis.key_compatible is not None:
        key_score = 1.0 if pair_analysis.key_compatible else 0.0
    else:
        key_score = harmonic_compatibility_score(current.key, candidate.key)

    weights = config.weights
    total = (
        drum_overlap * weights.drum_overlap
        + bpm_proximity * weights.bpm_proximity
        + bpm_trend * weights.bpm_trend
        + key_score * weights.key_compatibility
    )

    penalties: list[str] = []
    if not _same_style(current, candidate):
        total -= 0.30
        penalties.append("style_mismatch")
    if bpm_delta < 0:
        total -= config.descending_bpm_penalty
        penalties.append("bpm_descending")
    if bpm_abs_delta > config.preferred_bpm_diff:
        total -= config.over_preferred_bpm_penalty
        penalties.append("bpm_gap_over_preferred")

    return CandidateScore(
        total=_clamp01(total),
        drum_overlap=drum_overlap,
        bpm_proximity=bpm_proximity,
        bpm_trend=bpm_trend,
        key_compatibility=key_score,
        bpm_delta=bpm_delta,
        penalties=tuple(penalties),
    )

