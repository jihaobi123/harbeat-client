"""Live cut strategies — runtime decisions made while a track is playing.

  fast_cut       : within 5 seconds, find the next musically-acceptable cut
                   point (next downbeat or end of current phrase, whichever
                   comes first) and hard-cut to the next song WITHOUT changing
                   the playlist order.

  energy_up_cut  : swap the next song in the queue for one with higher dance
                   energy (compute_dance_energy), THEN apply the fast cut.

  energy_down_cut: same, but pick a lower-energy next song.
"""
from __future__ import annotations

from typing import Optional, Sequence

from .energy_hiphop import compute_dance_energy


def find_fast_cut_point(
    current_song,
    cursor_sec: float,
    max_wait_sec: float = 5.0,
) -> float:
    """Return the timestamp (sec into current_song) at which to cut.

    Preference order, all within `max_wait_sec`:
      1. Next downbeat
      2. Next beat
      3. cursor + 1 bar at current BPM (fallback)
    """
    deadline = cursor_sec + max_wait_sec

    for db in getattr(current_song, "downbeats", []) or []:
        if cursor_sec < db <= deadline:
            return float(db)

    for bp in getattr(current_song, "beat_points", []) or []:
        if cursor_sec < bp <= deadline:
            return float(bp)

    bpm = float(getattr(current_song, "bpm", None) or 100.0)
    bar = 4 * 60.0 / bpm
    return float(min(deadline, cursor_sec + bar))


def _swap_next_by_energy(
    queue: Sequence,
    current_index: int,
    pool: Sequence,
    direction: str,
) -> Optional[int]:
    """Find a song in `pool` (not already in queue at current_index+1..) with
    energy strictly higher (or lower) than the queued next, return its index in `pool`.
    """
    if current_index + 1 >= len(queue):
        return None
    cur_next_energy = compute_dance_energy(queue[current_index + 1]).total
    queued_ids = {getattr(q, "id", None) for q in queue}
    best_idx: Optional[int] = None
    best_score: Optional[float] = None
    for i, candidate in enumerate(pool):
        if getattr(candidate, "id", None) in queued_ids:
            continue
        e = compute_dance_energy(candidate).total
        diff = e - cur_next_energy
        if direction == "up" and diff <= 0:
            continue
        if direction == "down" and diff >= 0:
            continue
        score = abs(diff)
        if best_score is None or score > best_score:
            best_score = score
            best_idx = i
    return best_idx


def plan_cut(
    strategy: str,
    current_song,
    cursor_sec: float,
    queue: Sequence,
    current_index: int,
    pool: Sequence,
    max_wait_sec: float = 5.0,
) -> dict:
    """Build a CutPlan describing what audio-engine should do.

    Returns:
        {
          "strategy": strategy,
          "cut_at_sec": float,          # in current song
          "next_song_id": str | None,   # song to play next (may differ from queue)
          "swap": {"queue_index": i, "new_song_id": str} | None
        }
    """
    cut_at = find_fast_cut_point(current_song, cursor_sec, max_wait_sec)
    plan = {"strategy": strategy, "cut_at_sec": cut_at, "next_song_id": None, "swap": None}

    if strategy == "fast_cut":
        if current_index + 1 < len(queue):
            plan["next_song_id"] = getattr(queue[current_index + 1], "id", None)
        return plan

    direction = "up" if strategy == "energy_up_cut" else "down"
    pool_idx = _swap_next_by_energy(queue, current_index, pool, direction)
    if pool_idx is not None:
        new_song = pool[pool_idx]
        plan["next_song_id"] = getattr(new_song, "id", None)
        plan["swap"] = {"queue_index": current_index + 1, "new_song_id": plan["next_song_id"]}
    elif current_index + 1 < len(queue):
        # Could not find a swap candidate — fall back to the existing next song.
        plan["next_song_id"] = getattr(queue[current_index + 1], "id", None)
    return plan
