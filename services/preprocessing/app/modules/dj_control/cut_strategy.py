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


def _as_energy_100(value, default: float = 50.0) -> float:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return default
    if raw <= 1.0:
        raw *= 100.0
    return max(0.0, min(100.0, raw))


def _float_value(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _vocal_density_for_range(song, start: float, end: float) -> float:
    events = getattr(song, "vocal_events", None) or []
    if not isinstance(events, list) or not events or end <= start:
        return 0.55
    total = 0.0
    markers = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if "start" in event or "end" in event:
            ev_start = _float_value(event.get("start", event.get("time")), 0.0)
            ev_end = _float_value(event.get("end"), ev_start + _float_value(event.get("duration"), 0.0))
            confidence = _float_value(event.get("confidence"), 1.0)
            overlap = max(0.0, min(end, ev_end) - max(start, ev_start))
            total += overlap * confidence
        elif "time" in event and "type" in event:
            markers.append(event)
    if markers:
        active_start = None
        confidence = 1.0
        for marker in sorted(markers, key=lambda item: _float_value(item.get("time"), 0.0)):
            t = _float_value(marker.get("time"), 0.0)
            kind = str(marker.get("type") or "").lower()
            if kind == "enter":
                if active_start is None:
                    active_start = t
                    confidence = _float_value(marker.get("confidence"), 1.0)
                else:
                    confidence = max(confidence, _float_value(marker.get("confidence"), 1.0))
            elif kind == "exit" and active_start is not None:
                overlap = max(0.0, min(end, t) - max(start, active_start))
                total += overlap * confidence
                active_start = None
                confidence = 1.0
        if active_start is not None:
            overlap = max(0.0, end - max(start, active_start))
            total += overlap * confidence
    return min(1.0, total / (end - start))


def _section_energy_candidates(song) -> list[dict]:
    """Return entry-friendly section/curve energy candidates in 0..100.

    Energy cuts should feel like the selected bucket at the actual entry point,
    not merely match the song-wide average. We therefore inspect phrase_map and
    energy_curve, preferring musically useful early entry sections.
    """
    duration = float(getattr(song, "duration", 0) or 0)
    out: list[dict] = []

    phrases = getattr(song, "phrase_map", None) or []
    if isinstance(phrases, list):
        for idx, phrase in enumerate(phrases[:8]):
            if not isinstance(phrase, dict):
                continue
            start = float(phrase.get("start", phrase.get("start_sec", phrase.get("time", 0.0))) or 0.0)
            end = float(phrase.get("end", phrase.get("end_sec", start + 16.0)) or start + 16.0)
            if duration > 0 and start > max(75.0, duration * 0.55):
                continue
            label = str(phrase.get("label", phrase.get("type", "section")) or "section").lower()
            energy = _as_energy_100(phrase.get("energy", phrase.get("intensity")), _score(song))
            priority = {
                "drop": 1.0,
                "chorus": 0.95,
                "hook": 0.92,
                "intro": 0.85,
                "break": 0.82,
                "verse": 0.78,
                "build": 0.75,
            }.get(label, 0.68)
            out.append({
                "start": max(0.0, start),
                "end": max(end, start),
                "label": label,
                "energy": energy,
                "priority": priority,
                "vocal_density": _vocal_density_for_range(song, start, min(end, start + 8.0)),
                "source": "phrase_map",
            })

    curve = getattr(song, "energy_curve", None) or []
    if isinstance(curve, list):
        for point in curve:
            if isinstance(point, dict):
                t = float(point.get("time", point.get("sec", 0.0)) or 0.0)
                raw = point.get("energy", point.get("value"))
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                t = float(point[0] or 0.0)
                raw = point[1]
            else:
                continue
            if duration > 0 and t > max(75.0, duration * 0.55):
                continue
            out.append({
                "start": max(0.0, t),
                "end": max(0.0, t + 8.0),
                "label": "energy_peak",
                "energy": _as_energy_100(raw, _score(song)),
                "priority": 0.72,
                "vocal_density": _vocal_density_for_range(song, t, t + 8.0),
                "source": "energy_curve",
            })

    if not out:
        out.append({
            "start": 0.0,
            "end": min(duration, 16.0) if duration > 0 else 16.0,
            "label": "song_average",
            "energy": _score(song),
            "priority": 0.50,
            "vocal_density": _vocal_density_for_range(song, 0.0, 8.0),
            "source": "song_average",
        })
    return out


def _best_target_energy_segment(song, target_min: float, target_max: float) -> dict:
    candidates = _section_energy_candidates(song)
    best = max(
        candidates,
        key=lambda item: (
            _energy_match(float(item["energy"]), target_min, target_max),
            float(item.get("priority", 0.0)),
            float(item["energy"]),
        ),
    )
    match = _energy_match(float(best["energy"]), target_min, target_max)
    return {
        **best,
        "match": round(match, 4),
        "in_target": target_min <= float(best["energy"]) <= target_max,
        "vocal_density": round(float(best.get("vocal_density", 0.55)), 4),
    }


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
    bass_windows = getattr(song, "bass_risk_windows", None) or []
    penalty = min(0.30, 0.04 * len(bass_windows))
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
    segment = _best_target_energy_segment(candidate, target_min, target_max)
    segment_energy = float(segment["energy"])
    segment_match = _energy_match(segment_energy, target_min, target_max)
    whole_match = _energy_match(energy, target_min, target_max)
    breakdown = {
        "energy_match": round((0.72 * segment_match + 0.28 * whole_match), 4),
        "segment_energy_match": round(segment_match, 4),
        "song_energy_match": round(whole_match, 4),
        "segment_priority": round(float(segment.get("priority", 0.0)), 4),
        "segment_vocal_density": round(float(segment.get("vocal_density", 0.55)), 4),
        "segment_single_vocal_allowed": True,
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
        "target_segment": segment,
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
            [x for x in active if _song_id(x[0]) not in cached],
            [x for x in reserve if _song_id(x[0]) not in cached],
            library,
        ]
        for stage in stages:
            items = []
            for song, source in stage:
                item = _candidate_plan_item(
                    song,
                    current_song=current_song,
                    target_min=lo,
                    target_max=hi,
                    current_style=current_style,
                    source=source,
                    cached_ids=cached,
                    syncing_ids=syncing,
                )
                if item["target_segment"].get("in_target") or lo <= _score(song) <= hi:
                    items.append(item)
            selected = _select_best(items, prefer_cached=prefer_cached)
            if selected:
                fallback_reason = reason
                selected_range = (lo, hi)
                break
        if selected:
            break

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
    target_segment = selected["target_segment"]
    effective_energy = float(target_segment["energy"])
    fallback = fallback_reason is not None or not (target_min <= effective_energy <= target_max)
    selected_bucket = {
        "min": float(selected_range[0]),
        "max": float(selected_range[1]),
        "label": _target_label(selected_range[0], selected_range[1]),
    }
    reason = [
        f"目标区间为 {target['label']}，接入段落能量 {effective_energy:.0f}（整首 {profile['dance_energy_score']:.0f}）",
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
            "segment_energy_score": round(effective_energy, 1),
            "entry_start_sec": round(float(target_segment.get("start", 0.0)), 3),
            "entry_label": target_segment.get("label"),
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
        "recommended_transition_hint": "drop_swap" if effective_energy >= current_score else "filter_sweep_high",
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
    target_style_reserve_per_style: int = 2,
    include_styles: Sequence[str] | None = None,
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

    # Prepare style reserve pool
    supported_styles = list(include_styles or ["breaking", "hiphop", "jazz", "popping", "locking", "house", "krump", "waacking"])
    style_reserve_pool = {s: [] for s in supported_styles}
    style_pool_status = {}

    style_candidates = []
    for song in library_songs:
        sid = _song_id(song)
        if not sid or sid in active_set or sid in excluded:
            continue
        # Check if already in energy reserve pool
        if any(sid in songs for songs in reserve_pool.values()):
            continue

        for target_style in supported_styles:
            style_score = get_style_score(song, target_style)
            if style_score >= 0.40:  # Minimum threshold
                mix_score = _transition_window_score(song) * 0.35 + _risk_safety(song) * 0.20
                total = style_score + mix_score
                style_candidates.append((target_style, total, song, style_score))

    # Sort and distribute to style reserve pools
    style_candidates.sort(key=lambda item: item[1], reverse=True)
    for target_style, _total, song, style_score in style_candidates:
        if len(style_reserve_pool[target_style]) >= max(1, target_style_reserve_per_style):
            continue
        sid = _song_id(song)
        if sid not in [s for songs in style_reserve_pool.values() for s in songs]:
            style_reserve_pool[target_style].append(sid)
            # Add to energy_profiles if not already there
            if sid not in energy_profiles:
                energy_profiles[sid] = get_dance_energy_profile(song)

    # Calculate style pool status
    # Note: We don't have cache status here, this would need to be filled by router
    for s in supported_styles:
        count = len(style_reserve_pool[s])
        style_pool_status[s] = {
            "available": count,
            "cached": 0,  # To be filled by router with actual cache status
            "syncing": 0,  # To be filled by router
            "status": "ready" if count >= target_style_reserve_per_style else "insufficient" if count > 0 else "empty",
        }

    p0 = active_ids[:1]
    p1 = active_ids[1:2]
    p2 = active_ids[2:6]
    p3 = [sid for ids in reserve_pool.values() for sid in ids]
    p4 = [sid for ids in style_reserve_pool.values() for sid in ids]

    return {
        "active_queue": active_ids,
        "reserve_pool": reserve_pool,
        "energy_profiles": {
            sid: {"score": profile["dance_energy_score"], "bucket": profile["bucket"], **profile}
            for sid, profile in energy_profiles.items()
        },
        "sync_priority": {"p0": p0, "p1": p1, "p2": p2, "p3": p3, "p4": p4},
        "style_reserve_pool": style_reserve_pool,
        "style_pool_status": style_pool_status,
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


def get_style_score(song, target_style: str) -> float:
    """Get target dance style score from song."""
    scores = getattr(song, "dance_style_scores", None) or {}
    if isinstance(scores, dict) and target_style in scores:
        try:
            return max(0.0, min(1.0, float(scores[target_style])))
        except (TypeError, ValueError):
            pass

    # Fallback to genre_profile.style_evidence_v1
    genre_profile = getattr(song, "genre_profile", None) or {}
    if isinstance(genre_profile, dict):
        style_evidence = genre_profile.get("style_evidence_v1", {})
        if isinstance(style_evidence, dict) and target_style in style_evidence:
            evidence = style_evidence[target_style]
            if isinstance(evidence, dict) and "final_score" in evidence:
                try:
                    return max(0.0, min(1.0, float(evidence["final_score"])))
                except (TypeError, ValueError):
                    pass

    return 0.0


def _get_matched_labels(song, target_style: str) -> list[str]:
    """Extract matched labels from genre_profile for target style."""
    genre_profile = getattr(song, "genre_profile", None) or {}
    if not isinstance(genre_profile, dict):
        return []

    style_evidence = genre_profile.get("style_evidence_v1", {})
    if not isinstance(style_evidence, dict) or target_style not in style_evidence:
        return []

    evidence = style_evidence[target_style]
    if not isinstance(evidence, dict):
        return []

    # Extract from external_source_scores or local_breakdown
    matched = []

    external_sources = evidence.get("external_source_scores", {})
    if isinstance(external_sources, dict):
        for source, data in external_sources.items():
            if isinstance(data, dict) and data.get("matched_labels"):
                matched.extend(data["matched_labels"])

    local_breakdown = evidence.get("local_breakdown", {})
    if isinstance(local_breakdown, dict) and local_breakdown.get("matched_features"):
        matched.extend(local_breakdown["matched_features"])

    return list(set(matched))[:5]  # Return top 5 unique labels


def _style_transition_hint(from_style: str | None, to_style: str) -> str:
    """Recommend transition strategy hint based on style change."""
    if not from_style or from_style == to_style:
        return "harmonic_blend"

    # Style transition hint mapping
    hints = {
        ("hiphop", "popping"): "percussion_bridge",
        ("hiphop", "locking"): "percussion_bridge",
        ("hiphop", "breaking"): "drop_swap",
        ("hiphop", "house"): "auto_bpm_ramp",
        ("hiphop", "krump"): "impact_slam_cut",
        ("hiphop", "waacking"): "neutral_fx_bridge",
        ("hiphop", "jazz"): "harmonic_blend",
        ("jazz", "hiphop"): "harmonic_blend",
        ("jazz", "locking"): "percussion_bridge",
        ("jazz", "waacking"): "harmonic_blend",

        ("popping", "locking"): "eq_swap_4bar",
        ("popping", "house"): "harmonic_blend",
        ("popping", "breaking"): "percussion_bridge",

        ("locking", "house"): "auto_bpm_ramp",
        ("locking", "popping"): "eq_swap_4bar",

        ("house", "waacking"): "harmonic_blend",
        ("house", "krump"): "echo_out_hard_drop",

        ("krump", "house"): "neutral_fx_bridge",
        ("krump", "hiphop"): "breakdown_reset",

        ("breaking", "hiphop"): "drop_swap",
        ("breaking", "popping"): "percussion_bridge",
    }

    key = (from_style.lower(), to_style.lower())
    return hints.get(key, "echo_out_hard_drop")


def plan_target_style_cut(
    *,
    current_song,
    cursor_sec: float,
    target_style: str,
    active_queue: Sequence,
    style_reserve_pool: Sequence,
    library_pool: Sequence = (),
    current_style: str | None = None,
    played_song_ids: set[str] | None = None,
    blocked_song_ids: set[str] | None = None,
    exclude_song_ids: set[str] | None = None,
    cached_song_ids: set[str] | None = None,
    syncing_song_ids: set[str] | None = None,
    prefer_cached: bool = True,
    max_wait_sec: float = 5.0,
) -> dict:
    """Plan a target dance style cut."""
    played = set(played_song_ids or set())
    blocked = set(blocked_song_ids or set())
    excluded = set(exclude_song_ids or set()) | {_song_id(current_song)}
    cached = set(cached_song_ids or set())
    syncing = set(syncing_song_ids or set())

    current_profile = get_dance_energy_profile(current_song)
    current_energy = float(current_profile["dance_energy_score"])
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
    reserve = eligible(style_reserve_pool, "style_reserve_pool")
    active_ids = {sid for _song, _source in active for sid in [_song_id(_song)]}
    reserve_ids = {sid for _song, _source in reserve for sid in [_song_id(_song)]}
    library = [
        (song, "library_fallback")
        for song, _source in eligible(library_pool, "library_fallback")
        if _song_id(song) not in active_ids and _song_id(song) not in reserve_ids
    ]

    def score_candidate(song, source: str) -> dict:
        sid = _song_id(song)
        style_score = get_style_score(song, target_style)
        profile = get_dance_energy_profile(song)
        energy = float(profile["dance_energy_score"])

        # Calculate score components
        target_style_match = style_score

        # Transition safety
        transition_safety = _transition_window_score(song) * 0.60 + _risk_safety(song) * 0.40

        # Energy continuity (prefer similar energy, allow ±20 range)
        energy_diff = abs(energy - current_energy)
        if energy_diff <= 20:
            energy_continuity = 1.0 - (energy_diff / 40.0)
        elif energy_diff <= 35:
            energy_continuity = 0.50 - ((energy_diff - 20) / 60.0)
        else:
            energy_continuity = max(0.0, 0.25 - ((energy_diff - 35) / 100.0))

        # BPM compatibility
        bpm_compat = _bpm_compat(current_song, song)

        # Cache status
        cache_status = _cache_status(sid, cached, syncing)
        cache_ready = _cache_score(cache_status)

        # Novelty (avoid recently played)
        novelty = 0.80  # Default

        # Total score
        candidate_score = (
            0.45 * target_style_match
            + 0.20 * transition_safety
            + 0.15 * energy_continuity
            + 0.10 * bpm_compat
            + 0.05 * cache_ready
            + 0.05 * novelty
        )

        return {
            "song": song,
            "song_id": sid,
            "style_score": style_score,
            "energy_score": energy,
            "source": source,
            "cache_status": cache_status,
            "candidate_score": round(candidate_score, 4),
            "score_breakdown": {
                "target_style_match": round(target_style_match, 4),
                "transition_safety": round(transition_safety, 4),
                "energy_continuity": round(energy_continuity, 4),
                "bpm_compat": round(bpm_compat, 4),
                "cache_ready": round(cache_ready, 4),
                "novelty": round(novelty, 4),
            },
            "matched_labels": _get_matched_labels(song, target_style),
            "confidence": style_score,  # Use style_score as confidence
        }

    # Search stages: prefer cached first, then high-confidence, then fallback
    selected = None
    fallback_reason = None

    # Stage 1: active_queue + style_reserve_pool, cached, high confidence (>=0.75)
    for song, source in active + reserve:
        if _song_id(song) not in cached:
            continue
        candidate = score_candidate(song, source)
        if candidate["style_score"] >= 0.75:
            if selected is None or candidate["candidate_score"] > selected["candidate_score"]:
                selected = candidate

    # Stage 2: active_queue + style_reserve_pool, cached, usable (>=0.55)
    if not selected:
        for song, source in active + reserve:
            if _song_id(song) not in cached:
                continue
            candidate = score_candidate(song, source)
            if candidate["style_score"] >= 0.55:
                if selected is None or candidate["candidate_score"] > selected["candidate_score"]:
                    selected = candidate

    # Stage 3: active_queue + style_reserve_pool, not cached, high confidence
    if not selected:
        for song, source in active + reserve:
            if _song_id(song) in cached:
                continue
            candidate = score_candidate(song, source)
            if candidate["style_score"] >= 0.75:
                if selected is None or candidate["candidate_score"] > selected["candidate_score"]:
                    selected = candidate

    # Stage 4: library fallback, high confidence
    if not selected:
        fallback_reason = f"未在主队列和风格备选池找到 {target_style} 高置信候选，已从曲库扩展"
        for song, source in library:
            candidate = score_candidate(song, source)
            if candidate["style_score"] >= 0.55:
                if selected is None or candidate["candidate_score"] > selected["candidate_score"]:
                    selected = candidate

    # Stage 5: library fallback with relaxed threshold (>=0.40)
    if not selected:
        fallback_reason = f"未找到 {target_style} 高置信候选，已放宽标准从曲库选择相近风格"
        for song, source in library:
            candidate = score_candidate(song, source)
            if candidate["style_score"] >= 0.40:
                if selected is None or candidate["candidate_score"] > selected["candidate_score"]:
                    selected = candidate

    # No candidate found
    if selected is None:
        return {
            "intent": "target_dance_style",
            "strategy": "target_dance_style",
            "cut_at_sec": cut_at,
            "next_song_id": None,
            "current_song": {
                "song_id": _song_id(current_song),
                "dominant_style": current_style or "unknown",
                "energy_score": current_energy,
            },
            "target_style": target_style,
            "selected_song": None,
            "fallback": True,
            "fallback_reason": f"未找到可用的 {target_style} 风格候选",
            "reason": [f"当前曲库没有足够可信的 {target_style} 风格歌曲"],
        }

    # Build response
    song = selected["song"]
    is_fallback = fallback_reason is not None or selected["style_score"] < 0.75

    reason = [
        f"该歌曲 {target_style} 适配分 {selected['style_score']:.2f}",
    ]

    if selected["matched_labels"]:
        labels_str = " / ".join(selected["matched_labels"][:3])
        reason.append(f"命中 {labels_str} 标签")

    energy_diff = abs(selected["energy_score"] - current_energy)
    if energy_diff <= 20:
        reason.append(f"能量从 {current_energy:.0f} 到 {selected['energy_score']:.0f}，变化可控")
    elif energy_diff <= 35:
        reason.append(f"能量从 {current_energy:.0f} 到 {selected['energy_score']:.0f}，适度变化")
    else:
        reason.append(f"能量从 {current_energy:.0f} 到 {selected['energy_score']:.0f}，较大变化")

    if selected["score_breakdown"]["bpm_compat"] >= 0.65:
        reason.append("BPM 差较小或存在倍速关系")

    if selected["cache_status"] == "ready":
        reason.append("已在 RK 缓存，可立即切")
    elif selected["cache_status"] == "synchronizing":
        reason.append("正在同步到 RK")
    else:
        reason.append("未缓存，确认前会先同步")

    hint = _style_transition_hint(current_style, target_style)
    reason.append(f"推荐使用 {hint} 进行风格过渡")

    if fallback_reason:
        reason.insert(0, fallback_reason)

    return {
        "intent": "target_dance_style",
        "strategy": "target_dance_style",
        "cut_at_sec": cut_at,
        "next_song_id": selected["song_id"],
        "current_song": {
            "song_id": _song_id(current_song),
            "dominant_style": current_style or "unknown",
            "energy_score": current_energy,
        },
        "target_style": target_style,
        "selected_song": {
            "song_id": selected["song_id"],
            "title": getattr(song, "title", ""),
            "artist": getattr(song, "artist", ""),
            "style_score": selected["style_score"],
            "confidence": selected["confidence"],
            "matched_labels": selected["matched_labels"],
            "energy_score": selected["energy_score"],
            "cache_status": selected["cache_status"],
            "source": selected["source"],
        },
        "queue_action": {
            "type": "insert_next",
            "after_song_id": _song_id(current_song),
            "remove_from_style_reserve_pool": selected["source"] == "style_reserve_pool",
        },
        "candidate_score": selected["candidate_score"],
        "score_breakdown": selected["score_breakdown"],
        "recommended_transition_hint": hint,
        "reason": reason,
        "fallback": is_fallback,
        "fallback_reason": fallback_reason,
    }
