"""BPM compatibility and alignment planning."""

from __future__ import annotations

from .models import (
    BpmAlignmentPlan,
    BpmCompatibility,
    TempoRelation,
    TransitionConfig,
    TransitionMethod,
)


def assess_bpm_compatibility(
    from_bpm: float,
    to_bpm: float,
    config: TransitionConfig | None = None,
) -> BpmCompatibility:
    """Assess whether track B can be aligned to track A."""

    config = config or TransitionConfig()
    direct_delta = abs(from_bpm - to_bpm)
    if direct_delta <= config.max_direct_bpm_diff:
        return BpmCompatibility(
            is_mixable=True,
            relation=TempoRelation.DIRECT,
            target_b_bpm=from_bpm,
            effective_bpm_delta=direct_delta,
            reason="raw BPM difference is within direct transition limit",
        )

    double_target = from_bpm * 2.0
    double_delta = abs(double_target - to_bpm)
    half_target = from_bpm / 2.0
    half_delta = abs(half_target - to_bpm)

    if double_delta <= config.max_bpm_shift_for_ratio:
        return BpmCompatibility(
            is_mixable=True,
            relation=TempoRelation.B_IS_DOUBLE_A,
            target_b_bpm=double_target,
            effective_bpm_delta=double_delta,
            reason="track B can match track A as double-time within shift limit",
        )

    if half_delta <= config.max_bpm_shift_for_ratio:
        return BpmCompatibility(
            is_mixable=True,
            relation=TempoRelation.B_IS_HALF_A,
            target_b_bpm=half_target,
            effective_bpm_delta=half_delta,
            reason="track B can match track A as half-time within shift limit",
        )

    return BpmCompatibility(
        is_mixable=False,
        relation=TempoRelation.UNMATCHED,
        target_b_bpm=to_bpm,
        effective_bpm_delta=min(direct_delta, double_delta, half_delta),
        reason="BPM cannot match directly or by 1:2/2:1 relation within shift limit",
    )


def build_bpm_alignment_plan(
    from_bpm: float,
    to_bpm: float,
    method: TransitionMethod,
    config: TransitionConfig | None = None,
) -> BpmAlignmentPlan:
    """Build the playback-speed plan for the incoming track B."""

    config = config or TransitionConfig()
    compatibility = assess_bpm_compatibility(from_bpm, to_bpm, config)

    if method == TransitionMethod.FX_DIRECT_CUT or not compatibility.is_mixable:
        return BpmAlignmentPlan(
            from_bpm=from_bpm,
            to_original_bpm=to_bpm,
            to_entry_bpm=to_bpm,
            playback_rate=1.0,
            tempo_relation=TempoRelation.UNMATCHED,
            should_align_before_entry=False,
            restore_to_original_bpm=False,
            restore_bars=0,
            restore_curve=config.restore_curve,
            reason="direct FX cut uses B at original BPM without pre-entry tempo alignment",
        )

    entry_bpm = compatibility.target_b_bpm
    changed = abs(entry_bpm - to_bpm) > 0.001
    return BpmAlignmentPlan(
        from_bpm=from_bpm,
        to_original_bpm=to_bpm,
        to_entry_bpm=entry_bpm,
        playback_rate=entry_bpm / to_bpm,
        tempo_relation=compatibility.relation,
        should_align_before_entry=True,
        restore_to_original_bpm=changed,
        restore_bars=config.restore_bars if changed else 0,
        restore_curve=config.restore_curve,
        reason=compatibility.reason,
    )

