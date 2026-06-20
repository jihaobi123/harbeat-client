"""BPM grouping utilities for Smart Reorder."""
from __future__ import annotations

from typing import Any, Dict, List


def group_by_bpm(
    songs: List[Dict[str, Any]],
    tolerance: float = 0.03,
) -> List[List[Dict[str, Any]]]:
    """Group songs by BPM.

    Songs within the same group have BPM difference ≤ tolerance.

    Args:
        songs: Song list, each needs 'bpm' field.
        tolerance: BPM tolerance ratio (0.03 = ±3%).

    Returns:
        List of groups, each group is a list of songs.
    """
    if not songs:
        return []

    # Sort by BPM
    sorted_songs = sorted(songs, key=lambda s: s.get('bpm') or 120)

    groups: List[List[Dict[str, Any]]] = []
    current_group = [sorted_songs[0]]
    base_bpm = float(sorted_songs[0].get('bpm') or 120)

    for song in sorted_songs[1:]:
        bpm = float(song.get('bpm') or 120)
        if base_bpm <= 0:
            base_bpm = 120
        ratio = bpm / base_bpm

        if abs(ratio - 1.0) <= tolerance:
            # Belongs to current group
            current_group.append(song)
        else:
            # New group
            groups.append(current_group)
            current_group = [song]
            base_bpm = bpm

    # Don't forget last group
    if current_group:
        groups.append(current_group)

    return groups
