"""
Harmonize DJ Sequencing Engine (DJ.studio-inspired)
===================================================

Global-optimal playlist ordering for harmonic mixing:
  1. Pairwise scoring: Camelot Key + BPM compatibility + Energy curve
  2. Configurable harmonic weight: BPM-focused, Key-focused, or balanced
  3. Global optimization:
       - N ≤ 12: Held-Karp DP (exact TSP solution)
       - N > 12: Greedy nearest-neighbor + 2-opt local search
  4. Full-song playback with configurable overlap transitions
  5. Beat-aligned mix-in / mix-out point computation

Reference: DJ.studio Harmonize algorithm
  - Analyze millions of possible playlist combinations
  - Score each order for BPM and key compatibility (Camelot Wheel)
  - Return the sequence with the highest total harmonic score
  - Respect locked start/end positions
"""
from __future__ import annotations

import itertools
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from app.modules.library.analysis import camelot_distance, camelot_score

log = logging.getLogger(__name__)


# ── Song feature snapshot ──────────────────────────────────────────────────

@dataclass
class DJTrack:
    """All features the sequencer needs about a single song."""
    song_id: int
    title: str
    artist: str
    bpm: float
    camelot_key: str
    energy: float                     # 0.0 - 1.0
    duration: float                   # seconds
    key_confidence: float = 0.0       # 0.0 - 1.0
    downbeats: list[float] = field(default_factory=list)
    phrase_map: list[dict] = field(default_factory=list)
    beat_points: list[float] = field(default_factory=list)
    file_path: str = ""
    stem_files: dict[str, str] = field(default_factory=dict)


# ── Transition descriptor ──────────────────────────────────────────────────

@dataclass
class TransitionPlan:
    """How to transition from song A to song B."""
    from_song_id: int
    to_song_id: int
    score: float                       # composite compatibility (0-100)
    bpm_score: float
    key_score: float
    energy_score: float

    # Full-song play ranges
    a_play_start: float = 0.0
    a_play_end: float = 0.0
    b_play_start: float = 0.0
    b_play_end: float = 0.0

    # Overlap / transition zone
    overlap_bars: int = 8
    overlap_sec: float = 0.0
    mix_start_time: float = 0.0        # time in A where overlap begins
    b_cue_time: float = 0.0
    bpm_shift: float = 1.0
    mix_duration_bars: int = 8
    mix_duration_sec: float = 0.0

    # Gradual BPM transition (both tracks meet at target BPM during overlap)
    bpm_a_target: float = 0.0         # BPM track A adjusts to during overlap
    bpm_b_target: float = 0.0         # BPM track B adjusts to during overlap

    # Structure-aware section info
    a_section_out: str = ""            # section label of A where mix-out starts
    b_section_in: str = ""             # section label of B where mix-in starts

    # Auto-suggested transition style
    suggested_style: str = "smooth"


# ── Energy curve profiles ──────────────────────────────────────────────────

ENERGY_PROFILES = {
    "warmup": {"direction": "up", "tolerance": 0.25},
    "peak": {"direction": "sustain_high", "tolerance": 0.15},
    "cooldown": {"direction": "down", "tolerance": 0.25},
    "journey": {"direction": "arc", "tolerance": 0.2},
    "free": {"direction": "none", "tolerance": 1.0},
}

# ── Harmonic weight presets ────────────────────────────────────────────────

HARMONIC_WEIGHTS = {
    "bpm_first":  {"bpm": 0.60, "key": 0.25, "energy": 0.15},
    "key_first":  {"bpm": 0.25, "key": 0.60, "energy": 0.15},
    "balanced":   {"bpm": 0.40, "key": 0.40, "energy": 0.20},
}


# ── Pairwise scoring ──────────────────────────────────────────────────────

def _bpm_compatibility(bpm_a: float, bpm_b: float) -> float:
    """BPM compatibility score (0-100).
    ≤2% diff → 100, ≤5% → linear decay, ≤8% → gentle decay, >8% → 0.
    Also considers halftime/doubletime relationships.
    """
    if bpm_a <= 0 or bpm_b <= 0:
        return 0
    # Check direct ratio and halftime/doubletime
    ratios = [bpm_b / bpm_a, bpm_b / bpm_a * 2, bpm_b / bpm_a / 2]
    best = 0.0
    for ratio in ratios:
        diff_pct = abs(1.0 - ratio) * 100
        if diff_pct <= 2:
            s = 100.0
        elif diff_pct <= 5:
            s = 100 - (diff_pct - 2) * (40 / 3)   # 100→60
        elif diff_pct <= 8:
            s = 60 - (diff_pct - 5) * (60 / 3)     # 60→0
        else:
            s = 0
        best = max(best, s)
    return best


def _energy_compatibility(
    energy_a: float, energy_b: float,
    position_pct: float,
    profile: str = "journey",
) -> float:
    """Energy curve score (0-100) based on the desired profile."""
    cfg = ENERGY_PROFILES.get(profile, ENERGY_PROFILES["free"])
    direction = cfg["direction"]
    tolerance = cfg["tolerance"]
    diff = energy_b - energy_a

    if direction == "none":
        return 80
    if direction == "up":
        return 100 if diff >= 0 else max(0, 100 + diff / tolerance * 100)
    if direction == "down":
        return 100 if diff <= 0 else max(0, 100 - diff / tolerance * 100)
    if direction == "sustain_high":
        if energy_a >= 0.6 and energy_b >= 0.6:
            return max(0, 100 - abs(diff) / tolerance * 50)
        return max(0, min(energy_b, energy_a) / 0.6 * 60)
    if direction == "arc":
        if position_pct < 0.3:
            return _energy_compatibility(energy_a, energy_b, position_pct, "warmup")
        elif position_pct < 0.7:
            return _energy_compatibility(energy_a, energy_b, position_pct, "peak")
        else:
            return _energy_compatibility(energy_a, energy_b, position_pct, "cooldown")
    return 80


def score_pair(
    track_a: DJTrack, track_b: DJTrack,
    position_pct: float = 0.5,
    energy_profile: str = "journey",
    harmonic_weight: str = "balanced",
) -> TransitionPlan:
    """Compute DJ compatibility score between two tracks."""
    w = HARMONIC_WEIGHTS.get(harmonic_weight, HARMONIC_WEIGHTS["balanced"])
    bpm_s = _bpm_compatibility(track_a.bpm, track_b.bpm)
    key_s = float(camelot_score(track_a.camelot_key, track_b.camelot_key))
    energy_s = _energy_compatibility(
        track_a.energy, track_b.energy, position_pct, energy_profile
    )
    composite = bpm_s * w["bpm"] + key_s * w["key"] + energy_s * w["energy"]
    bpm_shift = track_a.bpm / track_b.bpm if track_b.bpm > 0 else 1.0

    return TransitionPlan(
        from_song_id=track_a.song_id,
        to_song_id=track_b.song_id,
        score=round(composite, 1),
        bpm_score=round(bpm_s, 1),
        key_score=round(key_s, 1),
        energy_score=round(energy_s, 1),
        bpm_shift=round(bpm_shift, 4),
    )


# ── Pairwise score matrix ─────────────────────────────────────────────────

def _build_score_matrix(
    tracks: list[DJTrack],
    energy_profile: str = "journey",
    harmonic_weight: str = "balanced",
) -> list[list[float]]:
    """Pre-compute all pairwise scores as a dense matrix."""
    n = len(tracks)
    matrix: list[list[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            plan = score_pair(
                tracks[i], tracks[j],
                position_pct=0.5,
                energy_profile=energy_profile,
                harmonic_weight=harmonic_weight,
            )
            matrix[i][j] = plan.score
    return matrix


# ── Held-Karp DP (exact TSP for small N) ──────────────────────────────────

def _solve_tsp_dp(
    matrix: list[list[float]], n: int,
    start_idx: Optional[int] = None,
) -> list[int]:
    """
    Held-Karp DP for TSP (maximum total edge weight path visiting all nodes).
    Complexity: O(n² · 2ⁿ). Safe for n ≤ 16.
    Returns ordered list of indices.
    """
    if n <= 1:
        return list(range(n))
    if n > 20:
        raise ValueError("DP TSP too expensive for n > 20")

    INF = float("-inf")
    # dp[mask][i] = best total score ending at node i, having visited nodes in mask
    dp = [[INF] * n for _ in range(1 << n)]
    parent = [[-1] * n for _ in range(1 << n)]

    # Initialize: start from each node (or fixed start)
    starts = [start_idx] if start_idx is not None else range(n)
    for s in starts:
        dp[1 << s][s] = 0

    for mask in range(1, 1 << n):
        for u in range(n):
            if not (mask & (1 << u)):
                continue
            if dp[mask][u] == INF:
                continue
            for v in range(n):
                if mask & (1 << v):
                    continue
                new_mask = mask | (1 << v)
                new_score = dp[mask][u] + matrix[u][v]
                if new_score > dp[new_mask][v]:
                    dp[new_mask][v] = new_score
                    parent[new_mask][v] = u

    # Find the best ending node
    full_mask = (1 << n) - 1
    best_end = max(range(n), key=lambda i: dp[full_mask][i])

    # Backtrack
    path = []
    mask = full_mask
    node = best_end
    while node != -1:
        path.append(node)
        prev = parent[mask][node]
        mask ^= (1 << node)
        node = prev
    path.reverse()
    return path


# ── Greedy + 2-opt (heuristic for larger N) ───────────────────────────────

def _solve_greedy(
    matrix: list[list[float]], n: int,
    start_idx: Optional[int] = None,
) -> list[int]:
    """Greedy nearest-neighbor construction."""
    if n <= 1:
        return list(range(n))

    visited = set()
    current = start_idx if start_idx is not None else 0
    path = [current]
    visited.add(current)

    while len(visited) < n:
        best_next = -1
        best_score = float("-inf")
        for j in range(n):
            if j in visited:
                continue
            if matrix[current][j] > best_score:
                best_score = matrix[current][j]
                best_next = j
        if best_next == -1:
            # Shouldn't happen, but add remaining
            for j in range(n):
                if j not in visited:
                    path.append(j)
                    visited.add(j)
            break
        path.append(best_next)
        visited.add(best_next)
        current = best_next

    return path


def _path_score(path: list[int], matrix: list[list[float]]) -> float:
    """Total edge score of a path."""
    return sum(matrix[path[i]][path[i + 1]] for i in range(len(path) - 1))


def _improve_2opt(
    path: list[int], matrix: list[list[float]],
    lock_start: bool = False,
    max_iterations: int = 500,
) -> list[int]:
    """Apply 2-opt swaps to improve total path score."""
    n = len(path)
    if n < 4:
        return path
    best = path[:]
    best_total = _path_score(best, matrix)
    improved = True
    iters = 0
    start_i = 1 if lock_start else 0

    while improved and iters < max_iterations:
        improved = False
        iters += 1
        for i in range(start_i, n - 2):
            for j in range(i + 2, n):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                cand_total = _path_score(candidate, matrix)
                if cand_total > best_total:
                    best = candidate
                    best_total = cand_total
                    improved = True

    return best


# ── Harmonize: global optimal ordering ─────────────────────────────────────

def harmonize(
    tracks: list[DJTrack],
    energy_profile: str = "journey",
    harmonic_weight: str = "balanced",
    start_song_id: Optional[int] = None,
) -> tuple[list[DJTrack], list[TransitionPlan]]:
    """
    DJ.studio Harmonize-inspired global sequencing.
    Finds the playlist ordering that maximizes total harmonic compatibility.
    """
    if len(tracks) <= 1:
        return tracks, []

    n = len(tracks)
    matrix = _build_score_matrix(tracks, energy_profile, harmonic_weight)

    # Determine locked start
    start_idx: Optional[int] = None
    if start_song_id:
        for i, t in enumerate(tracks):
            if t.song_id == start_song_id:
                start_idx = i
                break

    # Choose algorithm by size
    if n <= 16:
        path = _solve_tsp_dp(matrix, n, start_idx)
    else:
        path = _solve_greedy(matrix, n, start_idx)
        path = _improve_2opt(path, matrix, lock_start=start_idx is not None)

    # Build ordered tracks + transitions with position-aware energy scoring
    ordered = [tracks[i] for i in path]
    transitions: list[TransitionPlan] = []
    for i in range(len(ordered) - 1):
        position_pct = (i + 1) / len(ordered)
        plan = score_pair(
            ordered[i], ordered[i + 1],
            position_pct=position_pct,
            energy_profile=energy_profile,
            harmonic_weight=harmonic_weight,
        )
        transitions.append(plan)

    total = sum(t.score for t in transitions)
    avg = total / max(len(transitions), 1)
    log.info(
        "Harmonize: %d tracks, algorithm=%s, avg_score=%.1f, total=%.0f",
        n, "dp" if n <= 16 else "greedy+2opt", avg, total,
    )

    return ordered, transitions


# ── Structure-aware helpers ────────────────────────────────────────────────

def _find_outro_start(track: DJTrack) -> Optional[float]:
    """Find the start time of the outro or last suitable section for mix-out."""
    if not track.phrase_map:
        return None
    for section in track.phrase_map:
        if section.get("label", "").lower() == "outro":
            return section["start"]
    # Fallback: start of last section
    return track.phrase_map[-1]["start"]


def _find_intro_end(track: DJTrack) -> Optional[float]:
    """Find the end time of the intro or first suitable section for mix-in."""
    if not track.phrase_map:
        return None
    for section in track.phrase_map:
        if section.get("label", "").lower() == "intro":
            return section["end"]
    # Fallback: end of first section
    return track.phrase_map[0]["end"]


def _get_section_at(track: DJTrack, time_sec: float) -> str:
    """Return the label of the section containing the given time."""
    for section in track.phrase_map:
        start = section.get("start", 0)
        end = section.get("end", 0)
        if start <= time_sec < end or (time_sec == end == track.duration):
            return section.get("label", "")
    return ""


def _suggest_transition_style(
    track_a: DJTrack, track_b: DJTrack,
) -> str:
    """Auto-suggest the best transition style based on track characteristics."""
    energy_diff = track_b.energy - track_a.energy
    bpm_diff_pct = abs(track_a.bpm - track_b.bpm) / max(track_a.bpm, 1) * 100
    key_dist = camelot_distance(track_a.camelot_key, track_b.camelot_key)

    # High energy jump → slam (energy burst)
    if energy_diff > 0.3:
        return "slam"
    # Energy drop → echo_out (spacious reverb tail)
    if energy_diff < -0.25:
        return "echo_out"
    # Same key or adjacent → smooth (harmonic crossfade)
    if key_dist <= 1:
        return "smooth"
    # Large BPM difference → filter (mask tempo change with sweep)
    if bpm_diff_pct > 5:
        return "filter"
    # Similar energy + good key → bass_swap (classic DJ technique)
    if abs(energy_diff) < 0.1 and key_dist <= 2:
        return "bass_swap"
    # Default
    return "power"


# ── Transition params: mix-in / mix-out computation ────────────────────────

def compute_transition_params(
    track_a: DJTrack,
    track_b: DJTrack,
    plan: TransitionPlan,
    overlap_bars: int = 8,
) -> TransitionPlan:
    """
    Compute mix-in/mix-out points for a transition.

    Upgrades over basic approach:
      - Structure-aware: prefers Outro→Intro boundaries from phrase_map
      - Gradual BPM: both tracks meet at a mid-point tempo during overlap
      - Auto-suggest transition style based on energy/key/BPM relationship
    """
    bar_sec_a = _bars_to_seconds(1, track_a.bpm)
    bar_sec_b = _bars_to_seconds(1, track_b.bpm)

    # Limit overlap to a fraction of each song's duration
    max_overlap_a = track_a.duration * 0.3
    max_overlap_b = track_b.duration * 0.3
    overlap_sec_a = min(overlap_bars * bar_sec_a, max_overlap_a)
    overlap_sec_b = min(overlap_bars * bar_sec_b, max_overlap_b)
    overlap_sec = min(overlap_sec_a, overlap_sec_b)
    actual_bars = max(2, round(overlap_sec / bar_sec_a))

    # A plays from start to end
    plan.a_play_start = 0.0
    plan.a_play_end = track_a.duration

    # ── Structure-aware mix-out point ──
    # Prefer Outro start from phrase_map; fallback to duration - overlap
    outro_start = _find_outro_start(track_a)
    mix_out = track_a.duration - overlap_sec
    if outro_start is not None and outro_start > track_a.duration * 0.5:
        # Use Outro start if it's in the second half of the track
        mix_out = outro_start
        # Recompute overlap to match
        overlap_sec = track_a.duration - mix_out
        actual_bars = max(2, round(overlap_sec / bar_sec_a))

    if track_a.downbeats:
        mix_out = _snap_to_nearest(mix_out, track_a.downbeats)
    plan.mix_start_time = round(max(0, mix_out), 3)
    plan.a_section_out = _get_section_at(track_a, mix_out)

    # ── Structure-aware mix-in point ──
    # Prefer Intro end from phrase_map
    intro_end = _find_intro_end(track_b)
    b_cue = 0.0
    if intro_end is not None and intro_end < track_b.duration * 0.3:
        # B starts playing from beginning; overlap covers the intro
        b_cue = 0.0
    plan.b_play_start = 0.0
    plan.b_play_end = track_b.duration
    plan.b_cue_time = round(b_cue, 3)
    plan.b_section_in = _get_section_at(track_b, b_cue) if track_b.phrase_map else ""

    # Overlap
    plan.overlap_bars = actual_bars
    plan.overlap_sec = round(overlap_sec, 3)
    plan.mix_duration_bars = actual_bars
    plan.mix_duration_sec = round(overlap_sec, 3)

    # ── Gradual BPM transition ──
    if track_a.bpm > 0 and track_b.bpm > 0:
        bpm_diff = abs(track_a.bpm - track_b.bpm)
        if bpm_diff <= 8:
            # Small difference: both adjust to midpoint
            mid_bpm = (track_a.bpm + track_b.bpm) / 2
            plan.bpm_a_target = round(mid_bpm, 1)
            plan.bpm_b_target = round(mid_bpm, 1)
        else:
            # Larger difference: B adjusts to A's tempo
            plan.bpm_a_target = round(track_a.bpm, 1)
            plan.bpm_b_target = round(track_a.bpm, 1)

    # ── Auto-suggest transition style ──
    plan.suggested_style = _suggest_transition_style(track_a, track_b)

    return plan


# ── Helpers ────────────────────────────────────────────────────────────────

def _bars_to_seconds(bars: int, bpm: float) -> float:
    """Convert bars (4/4) to seconds."""
    if bpm <= 0:
        return 4.0
    return bars * 4 * 60.0 / bpm


def _snap_to_nearest(t: float, points: list[float]) -> float:
    """Snap a time value to the nearest point."""
    if not points:
        return t
    return min(points, key=lambda p: abs(p - t))


# ── Full pipeline ──────────────────────────────────────────────────────────

def build_dj_set(
    tracks: list[DJTrack],
    energy_profile: str = "journey",
    harmonic_weight: str = "balanced",
    overlap_bars: int = 8,
    start_song_id: Optional[int] = None,
) -> tuple[list[DJTrack], list[TransitionPlan]]:
    """
    Full DJ.studio-inspired pipeline:
      1. Harmonize: globally optimal track ordering (Camelot + BPM + Energy)
      2. Compute mix-in/mix-out points for each transition
    """
    ordered, transitions = harmonize(
        tracks, energy_profile, harmonic_weight, start_song_id,
    )

    for i, plan in enumerate(transitions):
        compute_transition_params(ordered[i], ordered[i + 1], plan, overlap_bars)

    log.info(
        "DJ set built: %d tracks, avg score=%.1f, overlap=%d bars",
        len(ordered),
        sum(t.score for t in transitions) / max(len(transitions), 1),
        overlap_bars,
    )

    return ordered, transitions
