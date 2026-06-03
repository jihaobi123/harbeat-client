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

from .energy_hiphop import compute_dance_energy, energy_bucket, get_dance_energy_profile


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


def _song_id(song) -> str:
    return str(getattr(song, "id", "") or "")


def _score(song) -> float:
    return float(get_dance_energy_profile(song)["dance_energy_score"])


def _style_score(song, style: str | None) -> float:
    if not style:
        return 0.5
    scores = getattr(song, "dance_style_scores", None) or {}
    if isinstance(scores, dict) and style in scores:
        try:
            return max(0.0, min(1.0, float(scores[style])))
        except (TypeError, ValueError):
            return 0.5
    return 0.5


def _bpm_compat(current_song, candidate) -> float:
    a = float(getattr(current_song, "bpm", 0) or 0)
    b = float(getattr(candidate, "bpm", 0) or 0)
    if a <= 0 or b <= 0:
        return 0.5
    ratio = abs(a - b) / max(a, b)
    half_double = abs((b / a) - 2.0) <= 0.08 or abs((b / a) - 0.5) <= 0.08
    if half_double:
        return 0.78
    return max(0.0, min(1.0, 1.0 - ratio / 0.22))


def _transition_window_score(song) -> float:
    score = 0.35
    if getattr(song, "transition_windows", None):
        score += 0.30
    if getattr(song, "cue_points", None):
        score += 0.10
    intro = getattr(song, "intro_clean_score", None)
    if intro is not None:
        score += 0.20 * max(0.0, min(1.0, float(intro)))
    return max(0.0, min(1.0, score))


def _risk_safety(song) -> float:
    vocal_events = getattr(song, "vocal_events", None) or []
    bass_windows = getattr(song, "bass_risk_windows", None) or []
    penalty = min(0.45, 0.04 * len(vocal_events) + 0.04 * len(bass_windows))
    stem_bonus = 0.10 if isinstance(getattr(song, "stems", None), dict) and getattr(song, "stems", None) else 0.0
    return max(0.0, min(1.0, 0.75 + stem_bonus - penalty))


def _cache_status(song_id: str, cached_ids: set[str], syncing_ids: set[str]) -> str:
    if song_id in cached_ids:
        return "ready"
    if song_id in syncing_ids:
        return "synchronizing"
    return "missing"


def _cache_score(status: str) -> float:
    return {"ready": 1.0, "synchronizing": 0.55, "missing": 0.10, "failed": 0.0}.get(status, 0.10)


def _target_label(min_score: float, max_score: float) -> str:
    return f"{int(min_score)}-{int(max_score)}"


def _energy_match(score: float, lo: float, hi: float) -> float:
    if lo <= score <= hi:
        center = (lo + hi) / 2.0
        half = max(1.0, (hi - lo) / 2.0)
        return max(0.75, 1.0 - abs(score - center) / (half * 2.0))
    if score < lo:
        return max(0.0, 1.0 - (lo - score) / 30.0)
    return max(0.0, 1.0 - (score - hi) / 30.0)


def _relaxed_ranges(target_min: float, target_max: float, current_score: float) -> list[tuple[float, float, str | None]]:
    ranges: list[tuple[float, float, str | None]] = [(target_min, target_max, None)]
    if target_min >= current_score:
        ranges.extend([
            (max(0.0, target_min - 5.0), target_max, f"未找到 {_target_label(target_min, target_max)} 区间歌曲，已放宽到 {_target_label(max(0.0, target_min - 5.0), target_max)}"),
            (max(0.0, target_min - 10.0), target_max, f"未找到 {_target_label(target_min, target_max)} 区间歌曲，已放宽到 {_target_label(max(0.0, target_min - 10.0), target_max)}"),
            (max(0.0, target_min - 10.0), 100.0, f"未找到 {_target_label(target_min, target_max)} 区间歌曲，已放宽到 {_target_label(max(0.0, target_min - 10.0), 100)}"),
            (current_score + 0.01, 100.0, "未找到目标区间歌曲，已放宽为高于当前能量"),
        ])
    elif target_max <= current_score:
        ranges.extend([
            (target_min, min(100.0, target_max + 5.0), f"未找到 {_target_label(target_min, target_max)} 区间歌曲，已放宽到 {_target_label(target_min, min(100.0, target_max + 5.0))}"),
            (max(0.0, target_min - 5.0), min(100.0, target_max + 10.0), f"未找到 {_target_label(target_min, target_max)} 区间歌曲，已放宽到 {_target_label(max(0.0, target_min - 5.0), min(100.0, target_max + 10.0))}"),
            (0.0, max(0.0, current_score - 0.01), "未找到目标区间歌曲，已放宽为低于当前能量"),
        ])
    else:
        ranges.extend([
            (max(0.0, target_min - 5.0), min(100.0, target_max + 5.0), f"未找到 {_target_label(target_min, target_max)} 区间歌曲，已放宽到 {_target_label(max(0.0, target_min - 5.0), min(100.0, target_max + 5.0))}"),
            (max(0.0, target_min - 10.0), min(100.0, target_max + 10.0), f"未找到 {_target_label(target_min, target_max)} 区间歌曲，已按接近目标中心选择"),
        ])
    seen = set()
    unique = []
    for lo, hi, reason in ranges:
        key = (round(lo, 2), round(hi, 2))
        if hi < lo or key in seen:
            continue
        seen.add(key)
        unique.append((lo, hi, reason))
    return unique


def _candidate_plan_item(
    candidate,
    *,
    current_song,
    target_min: float,
    target_max: float,
    current_style: str | None,
    source: str,
    cached_ids: set[str],
    syncing_ids: set[str],
) -> dict:
    profile = get_dance_energy_profile(candidate)
    song_id = _song_id(candidate)
    status = _cache_status(song_id, cached_ids, syncing_ids)
    energy = float(profile["dance_energy_score"])
    breakdown = {
        "energy_match": round(_energy_match(energy, target_min, target_max), 4),
        "style_match": round(_style_score(candidate, current_style), 4),
        "bpm_compat": round(_bpm_compat(current_song, candidate), 4),
        "transition_window": round(_transition_window_score(candidate), 4),
        "risk_safety": round(_risk_safety(candidate), 4),
        "cache_ready": round(_cache_score(status), 4),
    }
    score = (
        0.45 * breakdown["energy_match"]
        + 0.20 * breakdown["style_match"]
        + 0.15 * breakdown["bpm_compat"]
        + 0.10 * breakdown["transition_window"]
        + 0.05 * breakdown["risk_safety"]
        + 0.05 * breakdown["cache_ready"]
    )
    return {
        "song": candidate,
        "profile": profile,
        "source": source,
        "cache_status": status,
        "candidate_score": round(score, 4),
        "score_breakdown": breakdown,
    }


def _select_best(
    items: list[dict],
    *,
    prefer_cached: bool,
) -> dict | None:
    if not items:
        return None
    return max(
        items,
        key=lambda item: (
            1 if prefer_cached and item["cache_status"] == "ready" else 0,
            item["candidate_score"],
            item["profile"]["dance_energy_score"],
        ),
    )


def plan_target_energy_cut(
    *,
    current_song,
    cursor_sec: float,
    active_queue: Sequence,
    reserve_pool: Sequence,
    library_pool: Sequence = (),
    target_min: float,
    target_max: float,
    current_style: str | None = None,
    played_song_ids: set[str] | None = None,
    blocked_song_ids: set[str] | None = None,
    exclude_song_ids: set[str] | None = None,
    cached_song_ids: set[str] | None = None,
    syncing_song_ids: set[str] | None = None,
    prefer_cached: bool = True,
    max_wait_sec: float = 5.0,
) -> dict:
    """Preview a target-energy cut candidate from queue + reserve + library."""
    played = set(played_song_ids or set())
    blocked = set(blocked_song_ids or set())
    excluded = set(exclude_song_ids or set()) | {_song_id(current_song)}
    cached = set(cached_song_ids or set())
    syncing = set(syncing_song_ids or set())
    current_profile = get_dance_energy_profile(current_song)
    current_score = float(current_profile["dance_energy_score"])
    cut_at = find_fast_cut_point(current_song, cursor_sec, max_wait_sec)

    def eligible(seq: Sequence, source: str) -> list[tuple[object, str]]:
        out = []
        for song in seq:
            sid = _song_id(song)
            if not sid or sid in played or sid in blocked or sid in excluded:
                continue
            out.append((song, source))
        return out

    active = eligible(active_queue, "active_queue")
    reserve = eligible(reserve_pool, "reserve_pool")
    active_ids = {sid for _song, _source in active for sid in [_song_id(_song)]}
    reserve_ids = {sid for _song, _source in reserve for sid in [_song_id(_song)]}
    library = [
        (song, "library")
        for song, _source in eligible(library_pool, "library")
        if _song_id(song) not in active_ids and _song_id(song) not in reserve_ids
    ]

    selected = None
    fallback_reason = None
    selected_range = (target_min, target_max)
    for lo, hi, reason in _relaxed_ranges(target_min, target_max, current_score):
        stages = [
            [x for x in active if _song_id(x[0]) in cached],
            [x for x in reserve if _song_id(x[0]) in cached],
            *(
                [
                    [x for x in active if _song_id(x[0]) not in cached],
                    [x for x in reserve if _song_id(x[0]) not in cached],
                    library,
                ]
                if not prefer_cached or reason is not None
                else []
            ),
        ]
        if prefer_cached and reason is None:
            # If exact target has no cached song, try relaxed cached before
            # allowing an uncached exact candidate.
            stages.extend([])
        for stage in stages:
            items = [
                _candidate_plan_item(
                    song,
                    current_song=current_song,
                    target_min=lo,
                    target_max=hi,
                    current_style=current_style,
                    source=source,
                    cached_ids=cached,
                    syncing_ids=syncing,
                )
                for song, source in stage
                if lo <= _score(song) <= hi
            ]
            selected = _select_best(items, prefer_cached=prefer_cached)
            if selected:
                fallback_reason = reason
                selected_range = (lo, hi)
                break
        if selected:
            break
    if selected is None and prefer_cached:
        # Last chance: exact uncached candidates.
        items = [
            _candidate_plan_item(
                song,
                current_song=current_song,
                target_min=target_min,
                target_max=target_max,
                current_style=current_style,
                source=source,
                cached_ids=cached,
                syncing_ids=syncing,
            )
            for song, source in [*active, *reserve, *library]
            if target_min <= _score(song) <= target_max
        ]
        selected = _select_best(items, prefer_cached=False)

    target = {
        "min": float(target_min),
        "max": float(target_max),
        "label": _target_label(target_min, target_max),
    }
    if selected is None:
        return {
            "intent": "target_energy_bucket",
            "strategy": "target_energy_bucket",
            "cut_at_sec": cut_at,
            "next_song_id": None,
            "current_song": {
                "song_id": _song_id(current_song),
                "energy_score": current_profile["dance_energy_score"],
                "bucket": current_profile["bucket"],
            },
            "target_bucket": target,
            "selected_song": None,
            "fallback": True,
            "fallback_reason": "未找到可用目标能量候选",
            "reason": ["没有可用候选，保持原下一首或使用普通切歌"],
        }

    song = selected["song"]
    profile = selected["profile"]
    fallback = fallback_reason is not None or not (target_min <= profile["dance_energy_score"] <= target_max)
    selected_bucket = {
        "min": float(selected_range[0]),
        "max": float(selected_range[1]),
        "label": _target_label(selected_range[0], selected_range[1]),
    }
    reason = [
        f"目标区间为 {target['label']}，该歌曲能量 {profile['dance_energy_score']:.0f}",
        f"来源：{'主队列' if selected['source'] == 'active_queue' else '备选池' if selected['source'] == 'reserve_pool' else '曲库扩展'}",
        f"缓存状态：{'已缓存，可立即切' if selected['cache_status'] == 'ready' else '正在同步' if selected['cache_status'] == 'synchronizing' else '未缓存，确认前会先同步'}",
    ]
    if current_style:
        reason.append(f"舞种匹配当前 {current_style}")
    if selected["score_breakdown"]["bpm_compat"] >= 0.65:
        reason.append("BPM 差较小或存在倍速关系")
    if selected["score_breakdown"]["transition_window"] >= 0.60:
        reason.append("存在可用 transition window 或 clean intro")

    return {
        "intent": "target_energy_bucket",
        "strategy": "target_energy_bucket",
        "cut_at_sec": cut_at,
        "next_song_id": _song_id(song),
        "current_song": {
            "song_id": _song_id(current_song),
            "energy_score": current_profile["dance_energy_score"],
            "bucket": current_profile["bucket"],
        },
        "target_bucket": target,
        "effective_bucket": selected_bucket,
        "selected_song": {
            "song_id": _song_id(song),
            "title": getattr(song, "title", ""),
            "artist": getattr(song, "artist", ""),
            "energy_score": profile["dance_energy_score"],
            "bucket": profile["bucket"],
            "source": selected["source"],
            "cache_status": selected["cache_status"],
        },
        "queue_action": {
            "type": "insert_next",
            "after_song_id": _song_id(current_song),
            "remove_from_reserve_pool": selected["source"] == "reserve_pool",
        },
        "candidate_score": selected["candidate_score"],
        "score_breakdown": selected["score_breakdown"],
        "recommended_transition_hint": "drop_swap" if profile["dance_energy_score"] >= current_score else "filter_sweep_high",
        "reason": reason,
        "fallback": fallback,
        "fallback_reason": fallback_reason,
    }


def prepare_live_pool(
    *,
    active_queue: Sequence,
    library_songs: Sequence,
    style: str | None,
    target_reserve_per_bucket: int = 2,
    include_buckets: Sequence[str] | None = None,
    exclude_song_ids: set[str] | None = None,
) -> dict:
    excluded = set(exclude_song_ids or set())
    include = list(include_buckets or [f"{i}-{i + 10}" for i in range(0, 100, 10)])
    active_ids = [_song_id(song) for song in active_queue if _song_id(song)]
    energy_profiles = {}
    reserve_pool = {bucket: [] for bucket in include}

    for song in active_queue:
        sid = _song_id(song)
        if sid:
            energy_profiles[sid] = get_dance_energy_profile(song)

    candidates = []
    active_set = set(active_ids)
    for song in library_songs:
        sid = _song_id(song)
        if not sid or sid in active_set or sid in excluded:
            continue
        profile = get_dance_energy_profile(song)
        if profile["bucket"] not in reserve_pool:
            continue
        style_score = _style_score(song, style)
        mix_score = _transition_window_score(song) * 0.35 + _risk_safety(song) * 0.20
        candidates.append((profile["bucket"], style_score + mix_score, song, profile))
    candidates.sort(key=lambda item: item[1], reverse=True)
    for bucket, _score_val, song, profile in candidates:
        if len(reserve_pool[bucket]) >= max(1, target_reserve_per_bucket):
            continue
        sid = _song_id(song)
        reserve_pool[bucket].append(sid)
        energy_profiles[sid] = profile

    p0 = active_ids[:1]
    p1 = active_ids[1:2]
    p2 = active_ids[2:6]
    p3 = [ids[0] for ids in reserve_pool.values() if ids]
    return {
        "active_queue": active_ids,
        "reserve_pool": reserve_pool,
        "energy_profiles": {
            sid: {"score": profile["dance_energy_score"], "bucket": profile["bucket"], **profile}
            for sid, profile in energy_profiles.items()
        },
        "sync_priority": {"p0": p0, "p1": p1, "p2": p2, "p3": p3},
    }


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
