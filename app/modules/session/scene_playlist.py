"""C3 Scene Playlist Generator — generates sequenced playlists with DJ energy arcs.

Takes a SceneConfig + pool of analysed tracks → produces a sequenced playlist
that follows the standard DJ energy arc: warmup → build → peak → recover.

The generator does NOT select which tracks go in (that's the CandidateSelector);
it arranges them into a musically coherent order with proper energy pacing.

Design: stateless, pure function of (tracks, scene, duration).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .schemas import SceneConfig, SceneType

logger = logging.getLogger(__name__)

# ── Energy arc templates per scene type ──────────────────────────────────────
# Each arc is [phase_name, duration_fraction, (min_energy, max_energy), bpm_range]

ARC_TEMPLATES: dict[SceneType, list[dict]] = {
    SceneType.cypher: [
        {"phase": "warmup",  "pct": 0.20, "energy": (0.20, 0.45), "bpm": (75, 105),  "desc": "暖场：稳定 groove，让人愿意进圈"},
        {"phase": "build",   "pct": 0.30, "energy": (0.40, 0.65), "bpm": (85, 120),  "desc": "升温：能量爬升，鼓点变硬"},
        {"phase": "peak",    "pct": 0.35, "energy": (0.60, 0.95), "bpm": (95, 140),  "desc": "高潮：炸的、drop 明显的、舞者最嗨"},
        {"phase": "recover", "pct": 0.15, "energy": (0.30, 0.55), "bpm": (80, 115),  "desc": "回落：稳下来但不断气"},
    ],
    SceneType.practice: [
        {"phase": "warmup",  "pct": 0.15, "energy": (0.25, 0.50), "bpm": (75, 110),  "desc": "热身"},
        {"phase": "groove",  "pct": 0.05, "energy": (0.40, 0.60), "bpm": (80, 115),  "desc": "进入状态"},
        {"phase": "build",   "pct": 0.25, "energy": (0.50, 0.75), "bpm": (85, 125),  "desc": "练习主段"},
        {"phase": "peak",    "pct": 0.30, "energy": (0.60, 0.90), "bpm": (95, 135),  "desc": "高强度练习"},
        {"phase": "recover", "pct": 0.15, "energy": (0.30, 0.55), "bpm": (80, 115),  "desc": "放松"},
        {"phase": "close",   "pct": 0.10, "energy": (0.20, 0.45), "bpm": (75, 105),  "desc": "收尾"},
    ],
    SceneType.party: [
        {"phase": "warmup",  "pct": 0.15, "energy": (0.25, 0.50), "bpm": (80, 115),  "desc": "进场暖场"},
        {"phase": "build",   "pct": 0.25, "energy": (0.45, 0.70), "bpm": (95, 125),  "desc": "气氛升温"},
        {"phase": "peak",    "pct": 0.40, "energy": (0.65, 1.00), "bpm": (100, 140), "desc": "派对高潮"},
        {"phase": "recover", "pct": 0.15, "energy": (0.35, 0.60), "bpm": (85, 120),  "desc": "缓和"},
        {"phase": "close",   "pct": 0.05, "energy": (0.20, 0.40), "bpm": (75, 100),  "desc": "散场"},
    ],
    SceneType.battle_warmup: [
        {"phase": "warmup",  "pct": 0.25, "energy": (0.25, 0.50), "bpm": (80, 110),  "desc": "battle 前热身"},
        {"phase": "build",   "pct": 0.35, "energy": (0.45, 0.70), "bpm": (85, 120),  "desc": "进入状态"},
        {"phase": "peak",    "pct": 0.30, "energy": (0.60, 0.90), "bpm": (90, 130),  "desc": "赛前高峰"},
        {"phase": "recover", "pct": 0.10, "energy": (0.30, 0.55), "bpm": (80, 115),  "desc": "赛前整理"},
    ],
    SceneType.showcase: [
        {"phase": "intro",   "pct": 0.10, "energy": (0.20, 0.40), "bpm": (75, 105),  "desc": "开场"},
        {"phase": "build",   "pct": 0.20, "energy": (0.40, 0.65), "bpm": (85, 120),  "desc": "铺垫"},
        {"phase": "peak",    "pct": 0.40, "energy": (0.60, 1.00), "bpm": (95, 140),  "desc": "展示高潮"},
        {"phase": "climax",  "pct": 0.20, "energy": (0.65, 0.95), "bpm": (100, 140), "desc": "最高潮"},
        {"phase": "close",   "pct": 0.10, "energy": (0.25, 0.50), "bpm": (80, 115),  "desc": "收尾"},
    ],
}


@dataclass
class PlaylistTrack:
    """A track as placed in a generated playlist."""
    track_id: str
    order: int
    phase: str
    target_energy: float
    actual_energy: float
    bpm: float
    groove_score: float
    title: str = ""
    artist: str = ""
    genre: str = ""


@dataclass
class GeneratedPlaylist:
    """Output of the scene playlist generator."""
    scene: str
    total_duration_sec: float
    track_count: int
    tracks: list[PlaylistTrack] = field(default_factory=list)
    energy_arc: list[dict] = field(default_factory=list)
    phase_summary: dict[str, int] = field(default_factory=dict)


def generate_scene_playlist(
    tracks: list[dict],
    scene: SceneConfig,
    *,
    target_duration_sec: float = 1800,  # 30 min default
    avg_track_duration_sec: float = 180,  # 3 min avg
) -> GeneratedPlaylist:
    """Generate a sequenced playlist following the scene's energy arc.

    Args:
        tracks: list of track analysis dicts with at minimum:
                {track_id, bpm, energy, groove_score (or groove_profile.score),
                 title, artist, genre (or genre_profile.primary_genre)}
        scene: scene configuration (type, dance_styles, energy_start, etc.)
        target_duration_sec: desired total duration in seconds
        avg_track_duration_sec: average track duration for estimating count

    Returns:
        GeneratedPlaylist with sequenced tracks and metadata.
    """
    arc = ARC_TEMPLATES.get(scene.scene, ARC_TEMPLATES[SceneType.cypher])
    est_track_count = max(3, int(target_duration_sec / avg_track_duration_sec))

    # ── Categorize tracks by energy tier ────────────────────────────────
    low: list[dict] = []     # energy < 0.45
    mid: list[dict] = []     # 0.45 <= energy < 0.65
    high: list[dict] = []    # energy >= 0.65

    for t in tracks:
        e = float(t.get("energy", 0.5))
        bpm = float(t.get("bpm", 100))
        groove = float(
            (t.get("groove_profile", {}) or {}).get("score",
            t.get("groove_score", 0.5))
        )

        # Score for scene dance style match
        style_score = 0.0
        dance_scores = t.get("dance_style_scores", {})
        for style in scene.dance_styles:
            style_score = max(style_score, float(dance_scores.get(style, 0)))

        tagged = {**t, "_e": e, "_bpm": bpm, "_groove": groove, "_style": style_score}

        if e < 0.45:
            low.append(tagged)
        elif e < 0.65:
            mid.append(tagged)
        else:
            high.append(tagged)

    # ── Sort each tier by quality (style match + groove) ─────────────────
    def _quality(t: dict) -> float:
        return float(t["_style"]) * 0.5 + float(t["_groove"]) * 0.3 + float(t.get("beat_confidence", 0.5)) * 0.2

    low.sort(key=_quality, reverse=True)
    mid.sort(key=_quality, reverse=True)
    high.sort(key=_quality, reverse=True)

    # ── Assign tracks to phases ─────────────────────────────────────────
    sequenced: list[PlaylistTrack] = []
    used_ids: set[str] = set()  # prevent duplicate tracks across phases
    phase_pool_map = {
        "warmup": low, "intro": low,
        "groove": mid,
        "build": mid,
        "peak": high, "climax": high,
        "recover": mid + low,
        "close": low,
    }

    order = 0
    for phase_def in arc:
        phase_name = phase_def["phase"]
        n_tracks = max(1, int(est_track_count * phase_def["pct"]))
        e_lo, e_hi = phase_def["energy"]
        bpm_lo, bpm_hi = phase_def["bpm"]

        pool = phase_pool_map.get(phase_name, mid)

        phase_tracks = 0
        # First pass: exact energy + BPM match
        for t in pool:
            if phase_tracks >= n_tracks:
                break
            tid = str(t.get("track_id", t.get("song_id", "")))
            if tid in used_ids:
                continue
            e = t["_e"]
            bpm = t["_bpm"]
            if e_lo <= e <= e_hi and bpm_lo <= bpm <= bpm_hi:
                sequenced.append(_make_entry(t, order, phase_name))
                used_ids.add(tid)
                order += 1
                phase_tracks += 1

        # Second pass: relax BPM constraint
        if phase_tracks < n_tracks:
            for t in pool:
                if phase_tracks >= n_tracks:
                    break
                tid = str(t.get("track_id", t.get("song_id", "")))
                if tid in used_ids:
                    continue
                e = t["_e"]
                if e_lo <= e <= e_hi:
                    sequenced.append(_make_entry(t, order, phase_name))
                    used_ids.add(tid)
                    order += 1
                    phase_tracks += 1

        # Third pass: relax energy constraint
        if phase_tracks < n_tracks:
            for t in pool:
                if phase_tracks >= n_tracks:
                    break
                tid = str(t.get("track_id", t.get("song_id", "")))
                if tid in used_ids:
                    continue
                sequenced.append(_make_entry(t, order, phase_name))
                used_ids.add(tid)
                order += 1
                phase_tracks += 1

    # ── Build phase summary ──────────────────────────────────────────────
    from collections import Counter
    phase_counts = dict(Counter(t.phase for t in sequenced))

    # ── Build energy arc for visualization ───────────────────────────────
    energy_arc = []
    for phase_def in arc:
        phase_tracks_list = [t for t in sequenced if t.phase == phase_def["phase"]]
        if phase_tracks_list:
            avg_e = sum(t.actual_energy for t in phase_tracks_list) / len(phase_tracks_list)
            avg_bpm = sum(t.bpm for t in phase_tracks_list) / len(phase_tracks_list)
        else:
            avg_e = (phase_def["energy"][0] + phase_def["energy"][1]) / 2
            avg_bpm = (phase_def["bpm"][0] + phase_def["bpm"][1]) / 2
        energy_arc.append({
            "phase": phase_def["phase"],
            "target_energy": round(avg_e, 3),
            "avg_bpm": round(avg_bpm, 1),
            "track_count": len(phase_tracks_list),
            "desc": phase_def["desc"],
        })

    total_dur = sum(
        float(t.get("duration", avg_track_duration_sec))
        for t in tracks
        if str(t.get("track_id", t.get("song_id", ""))) in
        {pt.track_id for pt in sequenced}
    )

    logger.info(
        "[playlist] generated %d-track %s playlist: %s",
        len(sequenced), scene.scene.value,
        " → ".join(f"{p}({c})" for p, c in phase_counts.items()),
    )

    return GeneratedPlaylist(
        scene=scene.scene.value,
        total_duration_sec=round(total_dur, 1),
        track_count=len(sequenced),
        tracks=sequenced,
        energy_arc=energy_arc,
        phase_summary=phase_counts,
    )


def _make_entry(track: dict, order: int, phase: str) -> PlaylistTrack:
    gp = track.get("genre_profile", {}) or {}
    return PlaylistTrack(
        track_id=str(track.get("track_id", track.get("song_id", ""))),
        order=order,
        phase=phase,
        target_energy=round(float(track["_e"]), 3),
        actual_energy=round(float(track["_e"]), 3),
        bpm=round(float(track["_bpm"]), 1),
        groove_score=round(float(track["_groove"]), 3),
        title=str(track.get("title", "")),
        artist=str(track.get("artist", "")),
        genre=str(gp.get("primary_genre", "")),
    )
