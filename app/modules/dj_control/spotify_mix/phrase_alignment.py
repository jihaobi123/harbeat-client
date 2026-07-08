"""Phrase alignment for transition point selection.

Finds the best transition points by prioritizing musical structure boundaries:
1. Section boundaries (chorus→verse, verse→chorus)
2. 8/4 bar boundaries
3. Downbeats

This ensures transitions land on musically meaningful moments rather than
arbitrary timestamps.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def find_transition_point(
    track_a_analysis: Dict[str, Any],
    track_b_analysis: Dict[str, Any],
    target_point_a: float,
    search_range_bars: int = 8,
) -> Tuple[float, float]:
    """Find best-aligned transition point pair.

    Args:
        track_a_analysis: TrackAnalysisV2 dict with phrase_map, downbeats, etc.
        track_b_analysis: TrackAnalysisV2 dict.
        target_point_a: Desired exit point on track A (seconds).
        search_range_bars: Search within ±N bars from target.

    Returns:
        (best_exit_on_a, best_entry_on_b) in seconds.
    """
    phrases_a = track_a_analysis.get('phrase_map') or []
    downbeats_a = track_a_analysis.get('downbeats') or []

    if not downbeats_a:
        # No beat info, use target as-is
        return target_point_a, 0.0

    # Find nearest bar to target
    nearest_bar_idx = _find_nearest_bar(downbeats_a, target_point_a)

    best_score = -1.0
    best_exit = target_point_a
    best_entry = 0.0

    # Search within range
    for offset in range(-search_range_bars, search_range_bars + 1):
        candidate_idx = nearest_bar_idx + offset
        if candidate_idx < 0 or candidate_idx >= len(downbeats_a):
            continue

        exit_time = downbeats_a[candidate_idx]
        score = _score_transition_point(exit_time, phrases_a, downbeats_a, candidate_idx)

        if score > best_score:
            best_score = score
            best_exit = exit_time
            # For entry point, pick clean intro or first downbeat
            best_entry = _find_best_entry(track_b_analysis)

    return best_exit, best_entry


def _find_nearest_bar(downbeats: List[float], target: float) -> int:
    """Find index of downbeat nearest to target time."""
    if not downbeats:
        return 0
    min_dist = float('inf')
    best_idx = 0
    for i, db in enumerate(downbeats):
        dist = abs(db - target)
        if dist < min_dist:
            min_dist = dist
            best_idx = i
    return best_idx


def _score_transition_point(
    time: float,
    phrases: List[Dict[str, Any]],
    downbeats: List[float],
    bar_idx: int,
) -> float:
    """Score a potential transition point.

    Higher score = better transition point.

    Scoring factors:
        +50: Section boundary (intro→verse, verse→chorus)
        +30: 8-bar boundary
        +20: 4-bar boundary
        +10: Downbeat
        +[0-20]: Energy compatibility (if known)
    """
    score = 10.0  # Base score (downbeat)

    # Check if section boundary
    if _is_section_boundary(time, phrases):
        score += 50.0

    # Check if 8/4 bar boundary
    if bar_idx % 8 == 0:
        score += 30.0
    elif bar_idx % 4 == 0:
        score += 20.0

    # Could add energy compatibility if phrase intensity data available
    phrase = _find_phrase_at(time, phrases)
    if phrase and phrase.get('intensity'):
        # Bonus if exiting from peak or entering to peak
        intensity = phrase.get('intensity', 0.5)
        if intensity > 0.7 or intensity < 0.3:
            score += 10.0

    return score


def _is_section_boundary(time: float, phrases: List[Dict[str, Any]]) -> bool:
    """Check if time is at a section boundary (e.g., verse→chorus)."""
    for phrase in phrases:
        start = phrase.get('start') or phrase.get('time')
        if start is None:
            continue
        if abs(start - time) < 0.5:  # Within 0.5s tolerance
            # Check if it's a major section change
            label = str(phrase.get('label') or '').lower()
            if any(kw in label for kw in ['chorus', 'verse', 'bridge', 'drop', 'break']):
                return True
    return False


def _find_phrase_at(time: float, phrases: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find phrase containing the given time."""
    for phrase in phrases:
        start = phrase.get('start') or phrase.get('time') or 0.0
        duration = phrase.get('duration') or phrase.get('length') or 4.0
        if start <= time < start + duration:
            return phrase
    return None


def _find_best_entry(track_b_analysis: Dict[str, Any]) -> float:
    """Find best entry point on incoming track.

    Prioritize:
        1. Clean intro (no vocals/bass in first 8 bars)
        2. First chorus/drop
        3. First downbeat
    """
    # Check for hot cues
    hot_cues = track_b_analysis.get('dj_hot_cues') or []
    for cue in hot_cues:
        cue_type = str(cue.get('type') or '').lower()
        if 'intro' in cue_type or 'main' in cue_type:
            return float(cue.get('time') or 0.0)

    # Check for clean intro from stems analysis
    stems = track_b_analysis.get('stems') or {}
    vocal_events = stems.get('vocal_events') or []
    if vocal_events:
        # Find first vocal-free window
        for event in vocal_events:
            if event.get('type') == 'entry' and event.get('time', 0) > 4.0:
                # Enter just before vocals come in
                return max(0.0, event.get('time', 0) - 2.0)

    # Default: first downbeat or 0
    downbeats_b = track_b_analysis.get('downbeats') or []
    return downbeats_b[0] if downbeats_b else 0.0
