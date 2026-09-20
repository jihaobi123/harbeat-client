"""Transition method selection and full transition plan building."""

from __future__ import annotations

from .cue_points import select_auto_exit_cue
from .drums import drum_overlap_score
from .key_compatibility import harmonic_keys_compatible
from .models import PairAnalysis, TrackProfile, TransitionConfig, TransitionMethod, TransitionPlan
from .scoring import score_transition_candidate
from .tempo import assess_bpm_compatibility, build_bpm_alignment_plan


def _same_style(left: TrackProfile, right: TrackProfile) -> bool:
    return left.style.strip().lower() == right.style.strip().lower()


def _drum_overlap(left: TrackProfile, right: TrackProfile, pair_analysis: PairAnalysis) -> float:
    if pair_analysis.drum_overlap is not None:
        return max(0.0, min(1.0, pair_analysis.drum_overlap))
    return drum_overlap_score(left.drum_profile, right.drum_profile)


def _key_compatible(left: TrackProfile, right: TrackProfile, pair_analysis: PairAnalysis) -> bool:
    if pair_analysis.key_compatible is not None:
        return pair_analysis.key_compatible
    return harmonic_keys_compatible(left.key, right.key)


def _stem_quality(track: TrackProfile, pair_analysis: PairAnalysis) -> float:
    if pair_analysis.stem_quality is not None:
        return pair_analysis.stem_quality
    if track.stem_quality is not None:
        return track.stem_quality
    return 0.0


def choose_transition_method(
    current: TrackProfile,
    incoming: TrackProfile,
    config: TransitionConfig | None = None,
    pair_analysis: PairAnalysis | None = None,
) -> tuple[TransitionMethod, str]:
    """Choose one transition method using the rule order from the DJ brief."""

    config = config or TransitionConfig()
    pair_analysis = pair_analysis or PairAnalysis()

    bpm = assess_bpm_compatibility(current.bpm, incoming.bpm, config)
    if not bpm.is_mixable:
        return (
            TransitionMethod.FX_DIRECT_CUT,
            "BPM is outside direct and 1:2/2:1 compatible ranges",
        )

    if not _same_style(current, incoming):
        return (
            TransitionMethod.FX_SOFT_OVERLAP,
            "styles differ, so use short FX overlap instead of a dense blend",
        )

    drum = _drum_overlap(current, incoming, pair_analysis)
    if drum < config.drum_low_threshold:
        return (
            TransitionMethod.FX_SOFT_OVERLAP,
            "drum overlap is below low threshold",
        )

    if drum <= config.drum_high_threshold:
        return (
            TransitionMethod.MIX_BLEND,
            "drum overlap is in regular mix range",
        )

    key_ok = _key_compatible(current, incoming, pair_analysis)
    if not key_ok:
        return (
            TransitionMethod.MIX_BLEND,
            "drum overlap is high but keys are not harmonic",
        )

    stem_quality = _stem_quality(incoming, pair_analysis)
    if stem_quality < config.stem_quality_threshold:
        return (
            TransitionMethod.MIX_BLEND,
            "keys are harmonic but stem quality is below stem blend threshold",
        )

    return (
        TransitionMethod.STEM_BLEND,
        "drum overlap is high, keys are harmonic, and stem quality is reliable",
    )


def build_transition_plan(
    current: TrackProfile,
    incoming: TrackProfile,
    config: TransitionConfig | None = None,
    pair_analysis: PairAnalysis | None = None,
) -> TransitionPlan:
    """Build the full transition output between two tracks."""

    config = config or TransitionConfig()
    pair_analysis = pair_analysis or PairAnalysis()
    method, reason = choose_transition_method(current, incoming, config, pair_analysis)
    score = score_transition_candidate(current, incoming, config, pair_analysis)
    return TransitionPlan(
        from_track_id=current.id,
        to_track_id=incoming.id,
        method=method,
        exit_cue=select_auto_exit_cue(current, config),
        bpm_plan=build_bpm_alignment_plan(current.bpm, incoming.bpm, method, config),
        drum_overlap=_drum_overlap(current, incoming, pair_analysis),
        key_compatible=_key_compatible(current, incoming, pair_analysis),
        reason=reason,
        candidate_score=score,
    )

