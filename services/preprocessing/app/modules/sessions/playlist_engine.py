"""智能练舞歌单生成引擎 — Camelot 和谐混音 + BPM 兼容 + 多样性控制"""
from __future__ import annotations

import re
from typing import Iterable, Protocol


class TrackLike(Protocol):
    """鸭子类型：任何有 bpm / camelot_key / artist / duration 属性的对象"""
    bpm: float | None
    camelot_key: str | None
    artist: str
    duration: float


CAM_KEY_RE = re.compile(r"^(1[0-2]|[1-9])([ABab])$")


def harmonic_candidates(camelot_key: str) -> list[str]:
    """返回和谐混音 Key：同号、相邻号、同号异调。"""
    normalized = camelot_key.strip().upper()
    m = CAM_KEY_RE.match(normalized)
    if not m:
        return []

    number = int(m.group(1))
    mode = m.group(2)

    prev_number = 12 if number == 1 else number - 1
    next_number = 1 if number == 12 else number + 1
    opposite_mode = "B" if mode == "A" else "A"

    return [
        f"{number}{mode}",
        f"{prev_number}{mode}",
        f"{next_number}{mode}",
        f"{number}{opposite_mode}",
    ]


def bpm_compatible(prev_bpm: float, candidate_bpm: float, tolerance: float = 0.06) -> bool:
    lower = prev_bpm * (1 - tolerance)
    upper = prev_bpm * (1 + tolerance)
    return lower <= candidate_bpm <= upper


def _artist_of(track) -> str:
    return (getattr(track, "artist", "") or "").strip().lower()


def diversity_ok(sequence: list, candidate) -> bool:
    if len(sequence) < 2:
        return True
    last_two = sequence[-2:]
    cand_artist = _artist_of(candidate)
    if cand_artist and all(_artist_of(t) == cand_artist for t in last_two):
        return False
    return True


def build_practice_list(tracks: Iterable, target_duration_min: int) -> list:
    """
    从 tracks 池中构建练舞歌单。
    优先和谐混音 → BPM 相近 → 多样性，直到达到目标时长。
    """
    pool = [t for t in tracks if getattr(t, "bpm", None) and getattr(t, "camelot_key", None)]
    if not pool:
        # 退化：没有分析数据的歌也放进来
        pool = list(tracks)
    if not pool:
        return []

    target_sec = target_duration_min * 60
    sequence = [pool.pop(0)]
    total_dur = getattr(sequence[0], "duration", 0) or 180  # 默认 3 分钟

    while pool and total_dur < target_sec:
        prev = sequence[-1]
        prev_bpm = getattr(prev, "bpm", None)
        prev_key = getattr(prev, "camelot_key", None)

        if prev_bpm and prev_key:
            harmonic = set(harmonic_candidates(prev_key))

            strict = [
                t for t in pool
                if getattr(t, "camelot_key", None) in harmonic
                and bpm_compatible(prev_bpm, getattr(t, "bpm", 0) or 0)
                and diversity_ok(sequence, t)
            ]
            medium = [
                t for t in pool
                if bpm_compatible(prev_bpm, getattr(t, "bpm", 0) or 0)
                and diversity_ok(sequence, t)
            ]
            loose = [t for t in pool if diversity_ok(sequence, t)]
            candidates = strict or medium or loose or pool
            chosen = min(candidates, key=lambda t: abs((getattr(t, "bpm", 0) or 0) - prev_bpm))
        else:
            chosen = pool[0]

        sequence.append(chosen)
        pool.remove(chosen)
        total_dur += getattr(chosen, "duration", 0) or 180

    return sequence
