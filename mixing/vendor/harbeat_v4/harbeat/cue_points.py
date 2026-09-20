"""Exit cue selection for automatic and manual transitions."""

from __future__ import annotations

import math

from .models import CuePoint, PhraseMarker, SectionMarker, TrackProfile, TransitionConfig


_CHORUS_NAMES = {"chorus", "hook", "refrain", "drop", "副歌"}


def bar_duration_seconds(bpm: float, beats_per_bar: int = 4) -> float:
    return (60.0 / bpm) * beats_per_bar


def _find_second_chorus(track: TrackProfile) -> SectionMarker | None:
    chorus_sections = [
        section
        for section in track.sections
        if section.name.strip().lower() in _CHORUS_NAMES or section.name.strip() in _CHORUS_NAMES
    ]
    chorus_sections.sort(key=lambda section: (section.occurrence, section.start_time_seconds))
    for section in chorus_sections:
        if section.occurrence == 2:
            return section
    if len(chorus_sections) >= 2:
        return chorus_sections[1]
    return None


def _fallback_bar_cue(track: TrackProfile, limit_seconds: float, reason: str, config: TransitionConfig) -> CuePoint:
    bar_seconds = bar_duration_seconds(track.bpm, config.beats_per_bar)
    bar_index = max(0, math.floor(limit_seconds / bar_seconds))
    return CuePoint(
        time_seconds=bar_index * bar_seconds,
        bar_index=bar_index,
        phrase_bars=1,
        reason=reason,
    )


def _latest_phrase_before(
    phrase_markers: tuple[PhraseMarker, ...],
    limit_seconds: float,
    accepted_phrase_bars: tuple[int, ...],
) -> PhraseMarker | None:
    accepted = [
        marker
        for marker in phrase_markers
        if marker.is_downbeat
        and marker.time_seconds <= limit_seconds
        and marker.phrase_bars in accepted_phrase_bars
    ]
    if not accepted:
        accepted = [
            marker
            for marker in phrase_markers
            if marker.is_downbeat and marker.time_seconds <= limit_seconds
        ]
    if not accepted:
        return None
    return max(accepted, key=lambda marker: (marker.time_seconds, marker.phrase_bars))


def select_auto_exit_cue(
    track: TrackProfile,
    config: TransitionConfig | None = None,
) -> CuePoint:
    """Select the automatic outgoing cue for track A."""

    config = config or TransitionConfig()
    second_chorus = _find_second_chorus(track)
    hard_limit = config.auto_max_play_seconds

    if track.duration_seconds is not None:
        hard_limit = min(hard_limit, track.duration_seconds)

    if second_chorus:
        limit_seconds = min(second_chorus.end_time_seconds, hard_limit)
        reason = "last preferred phrase before second chorus end or max play limit"
    else:
        limit_seconds = hard_limit
        reason = "last preferred phrase before max play limit"

    marker = _latest_phrase_before(track.phrase_markers, limit_seconds, config.preferred_auto_phrase_bars)
    if marker:
        return CuePoint(
            time_seconds=marker.time_seconds,
            bar_index=marker.bar_index,
            phrase_bars=marker.phrase_bars,
            reason=reason,
            risk_score=marker.risk_score,
        )

    return _fallback_bar_cue(track, limit_seconds, reason, config)


def _section_at(track: TrackProfile, time_seconds: float) -> SectionMarker | None:
    for section in track.sections:
        if section.contains(time_seconds):
            return section
    return None


def select_manual_exit_cue(
    track: TrackProfile,
    current_time_seconds: float,
    config: TransitionConfig | None = None,
) -> CuePoint:
    """Select a manual-cut cue no later than config.manual_max_wait_bars."""

    config = config or TransitionConfig()
    wait_window_seconds = bar_duration_seconds(track.bpm, config.beats_per_bar) * config.manual_max_wait_bars
    latest_allowed = current_time_seconds + wait_window_seconds

    candidates = [
        marker
        for marker in track.phrase_markers
        if marker.is_downbeat
        and current_time_seconds <= marker.time_seconds <= latest_allowed
        and marker.phrase_bars in config.manual_phrase_bars
    ]

    if not candidates:
        bar_seconds = bar_duration_seconds(track.bpm, config.beats_per_bar)
        next_bar = math.ceil(current_time_seconds / bar_seconds)
        cue_time = min(next_bar * bar_seconds, latest_allowed)
        return CuePoint(
            time_seconds=cue_time,
            bar_index=next_bar,
            phrase_bars=1,
            reason="nearest inferred downbeat within manual wait limit",
        )

    current_section = _section_at(track, current_time_seconds)
    is_dense = current_section is not None and current_section.density.average >= config.dense_section_threshold

    if is_dense:
        safe_candidates = [
            marker for marker in candidates if marker.risk_score <= config.manual_safe_risk_threshold
        ]
        if safe_candidates:
            chosen = min(safe_candidates, key=lambda marker: (marker.time_seconds, marker.risk_score))
            reason = "earliest safe phrase boundary after dense section"
        else:
            chosen = min(candidates, key=lambda marker: (marker.risk_score, marker.time_seconds))
            reason = "lowest-risk phrase boundary within manual wait limit"
    else:
        chosen = min(candidates, key=lambda marker: (marker.time_seconds, marker.risk_score))
        reason = "nearest phrase boundary after manual cut request"

    return CuePoint(
        time_seconds=chosen.time_seconds,
        bar_index=chosen.bar_index,
        phrase_bars=chosen.phrase_bars,
        reason=reason,
        risk_score=chosen.risk_score,
    )

