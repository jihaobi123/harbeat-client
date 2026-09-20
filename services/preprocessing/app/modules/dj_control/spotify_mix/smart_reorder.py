"""Smart Reorder: Camelot Wheel shortest-path sorting."""
from __future__ import annotations

from typing import Any, Dict, List

from .bpm_grouping import group_by_bpm
from .camelot_distance import camelot_distance


def smart_reorder(
    songs: List[Dict[str, Any]],
    bpm_tolerance: float = 0.03,
    prefer_energy_flow: bool = True,
) -> List[Dict[str, Any]]:
    """Smart Reorder: intelligent reordering by BPM + Camelot Key.

    Algorithm:
        1. Group by BPM (±3%)
        2. Within each group, use greedy Camelot Wheel sort
        3. Optional: prioritize smooth energy flow

    Args:
        songs: Song list (needs bpm, camelot_key, energy).
        bpm_tolerance: BPM grouping tolerance.
        prefer_energy_flow: Whether to prioritize smooth energy flow.

    Returns:
        Reordered song list.
    """
    if len(songs) <= 1:
        return songs

    # 1. Group by BPM
    groups = group_by_bpm(songs, tolerance=bpm_tolerance)

    # 2. Sort within each group by Camelot
    reordered: List[Dict[str, Any]] = []
    for group in groups:
        sorted_group = _sort_by_camelot_path(group, prefer_energy_flow)
        reordered.extend(sorted_group)

    # 3. Smooth inter-group BPM transitions (optional optimization)
    reordered = _smooth_bpm_transitions(reordered)

    return reordered


def _sort_by_camelot_path(
    songs: List[Dict[str, Any]],
    prefer_energy_flow: bool,
) -> List[Dict[str, Any]]:
    """Greedy Camelot Wheel sort.

    Strategy: At each step, pick the next song with shortest Camelot distance.
    """
    if len(songs) <= 1:
        return songs

    # Pick starting point: prefer lowest energy (suitable for low-to-high progression)
    if prefer_energy_flow:
        start_song = min(songs, key=lambda s: s.get('energy') or 0.5)
    else:
        start_song = songs[0]

    result = [start_song]
    remaining = [s for s in songs if s is not start_song]

    while remaining:
        current_key = result[-1].get('camelot_key') or ''

        if not current_key:
            # Current song has no key info, pick randomly
            next_song = remaining[0]
        else:
            # Pick the one with minimum Camelot distance
            best_candidate = None
            best_score = float('inf')

            for candidate in remaining:
                cand_key = candidate.get('camelot_key') or ''
                if not cand_key:
                    score = 10.0  # Penalty for missing key
                else:
                    try:
                        score = float(camelot_distance(current_key, cand_key))
                    except ValueError:
                        score = 10.0

                # If preferring energy flow, add energy difference penalty
                if prefer_energy_flow:
                    energy_diff = abs(
                        (candidate.get('energy') or 0.5) -
                        (result[-1].get('energy') or 0.5)
                    )
                    score += energy_diff * 2

                if score < best_score:
                    best_score = score
                    best_candidate = candidate

            next_song = best_candidate or remaining[0]

        result.append(next_song)
        remaining.remove(next_song)

    return result


def _smooth_bpm_transitions(songs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Smooth inter-group BPM transitions (optional optimization).

    If BPM jump detected, try to find a bridge song from previous group.
    """
    # For now, return original sequence; can optimize in later iterations
    return songs
