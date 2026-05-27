"""Vibe Search — Spotify-style audio-feature targeting.

Replaces the old CLAP (Contrastive Language-Audio Pretraining) embedding pipeline,
which required a 1.4GB model and slow GPU inference. This module mimics Spotify's
recommendations API approach instead:

  1. Parse the free-form query into a *target audio profile*:
       - target_tempo (BPM range)
       - target_energy (low/medium/high)
       - seed_genres (style hints)
       - mood_keywords (additional adjective tokens)
       - era (decade hint)

  2. Score each catalog ``Song`` (joined with ``SongTag``) against the target
     profile using weighted distance metrics:
       - BPM:    triangular kernel, width ±20
       - Energy: categorical match (low/medium/high)
       - Style: bidirectional substring + alias map
       - Mood/era: token overlap on title+artist+groove_tag

  3. Return the top-K, shaped exactly like the mobile ``VibeSearchResult`` /
     ``VibeSong`` models expect (``in_library``, ``match_percentage``,
     ``style``, ``energy``, ``source='catalog'``).

The result list is also usable as input to ``import-from-vibe`` — that endpoint
just delegates each item through ``add_song_to_library``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Song, SongTag


# ───────────────────── Intent parsing ───────────────────── #

# BPM described in plain English/Chinese. Mirrors what Spotify's
# "target_tempo" buckets cover. Triangular weighting later picks
# the center value.
_BPM_BUCKETS: list[tuple[tuple[str, ...], int, int]] = [
    (("chill", "lofi", "lo-fi", "slow", "ballad", "舒缓", "慢", "放松"), 65, 88),
    (("groove", "mid", "midtempo", "中速", "律动", "soul", "r&b", "rnb"), 88, 105),
    (("party", "club", "house", "dance", "派对", "舞曲"), 110, 124),
    (("hype", "hiphop", "hip-hop", "trap", "炸场", "嘻哈", "热血"), 85, 102),
    (("rave", "edm", "techno", "drumandbass", "dnb", "猛", "嗨"), 124, 150),
]

_ENERGY_LEXICON: dict[str, tuple[str, ...]] = {
    "low":    ("chill", "lofi", "lo-fi", "slow", "calm", "relax", "soft", "smooth",
               "舒缓", "放松", "慢", "轻", "冷", "柔"),
    "medium": ("groove", "soul", "r&b", "rnb", "midtempo", "vibe", "mellow",
               "律动", "中", "氛围"),
    "high":   ("hype", "explosive", "banger", "fire", "rage", "drop", "intense",
               "炸", "嗨", "猛", "热", "燃", "battle", "cypher", "rave"),
}

# Style aliases — map free-form keywords to canonical SongTag.style values.
_STYLE_ALIASES: dict[str, list[str]] = {
    "hiphop":    ["hip-hop", "hip hop", "hiphop", "嘻哈", "rap"],
    "trap":      ["trap", "陷阱"],
    "house":     ["house", "deep house", "tech house", "浩室"],
    "techno":    ["techno", "techy"],
    "edm":       ["edm", "electronic", "电子"],
    "rnb":       ["rnb", "r&b", "r and b", "soul", "灵魂", "节奏布鲁斯"],
    "pop":       ["pop", "流行"],
    "funk":      ["funk", "放克"],
    "jazz":      ["jazz", "爵士"],
    "rock":      ["rock", "摇滚"],
    "breaking":  ["breaking", "breakbeat", "bboy", "b-boy", "霹雳"],
    "popping":   ["popping", "popin", "机械", "震感"],
    "locking":   ["locking", "锁舞"],
    "waacking":  ["waacking", "甩手"],
    "krump":     ["krump"],
    "house_dance": ["house dance", "house-dance"],
    "latin":     ["latin", "salsa", "reggaeton", "拉丁"],
    "afro":      ["afro", "afrobeat", "afro house", "非洲"],
    "dancehall": ["dancehall"],
}

_GROOVE_ALIASES: dict[str, list[str]] = {
    "cypher":   ["cypher", "围圈", "围"],
    "battle":   ["battle", "对战", "斗舞"],
    "showcase": ["showcase", "表演", "舞台"],
    "training": ["training", "练习", "基础"],
    "party":    ["party", "派对", "club"],
    "warmup":   ["warmup", "warm up", "热身", "暖场"],
}

_ERA_RE = re.compile(r"(\d{2})s|(19|20)\d{2}|(\d{2,4})\s*年代|(old\s*school|oldschool|new\s*school)")
_BPM_RE = re.compile(r"(\d{2,3})\s*(?:bpm|拍)?", re.IGNORECASE)


@dataclass
class VibeProfile:
    raw: str
    bpm_center: Optional[float] = None
    bpm_min: Optional[float] = None
    bpm_max: Optional[float] = None
    energy: Optional[str] = None        # 'low' | 'medium' | 'high'
    styles: list[str] = field(default_factory=list)
    grooves: list[str] = field(default_factory=list)
    era_hint: Optional[str] = None
    mood_tokens: set[str] = field(default_factory=set)

    @property
    def is_empty(self) -> bool:
        return not (
            self.bpm_center or self.energy or self.styles
            or self.grooves or self.era_hint or self.mood_tokens
        )


def parse_intent(query: str) -> VibeProfile:
    """Free-form text → VibeProfile."""
    q = (query or "").lower().strip()
    profile = VibeProfile(raw=query or "")
    if not q:
        return profile

    # Explicit BPM numbers always win.
    bpm_match = _BPM_RE.search(q)
    if bpm_match:
        try:
            n = int(bpm_match.group(1))
            if 50 <= n <= 200:
                profile.bpm_center = float(n)
                profile.bpm_min = float(n - 8)
                profile.bpm_max = float(n + 8)
        except ValueError:
            pass

    # BPM buckets from descriptive words (only if no explicit number).
    if profile.bpm_center is None:
        for words, lo, hi in _BPM_BUCKETS:
            if any(w in q for w in words):
                profile.bpm_min = float(lo)
                profile.bpm_max = float(hi)
                profile.bpm_center = (lo + hi) / 2.0
                break

    # Energy
    for bucket, words in _ENERGY_LEXICON.items():
        if any(w in q for w in words):
            profile.energy = bucket
            break

    # Styles
    for canonical, words in _STYLE_ALIASES.items():
        if any(w in q for w in words):
            profile.styles.append(canonical)

    # Grooves
    for canonical, words in _GROOVE_ALIASES.items():
        if any(w in q for w in words):
            profile.grooves.append(canonical)

    # Era
    era_match = _ERA_RE.search(q)
    if era_match:
        profile.era_hint = era_match.group(0)

    # Mood tokens = leftover Chinese chars + English words for soft matching.
    profile.mood_tokens = set(re.findall(r"[\u4e00-\u9fff]|[a-z][a-z'\-]{2,}", q))

    return profile


# ───────────────────── Scoring ───────────────────── #

def _bpm_score(song_bpm: Optional[float], profile: VibeProfile) -> float:
    """Triangular kernel centered on profile.bpm_center, width=20."""
    if profile.bpm_center is None or song_bpm is None:
        return 0.0
    delta = abs(song_bpm - profile.bpm_center)
    width = max(15.0, (profile.bpm_max or profile.bpm_center + 15) - profile.bpm_center)
    if delta > width * 2:
        return 0.0
    return max(0.0, 1.0 - delta / (width * 2))


def _energy_score(song_energy: Optional[str], profile_energy: Optional[str]) -> float:
    if not profile_energy:
        return 0.0
    if not song_energy:
        return 0.0
    return 1.0 if song_energy.lower() == profile_energy else 0.0


def _style_score(tag_style: Optional[str], tag_groove: Optional[str], profile: VibeProfile) -> float:
    if not (profile.styles or profile.grooves):
        return 0.0
    hits = 0
    total = max(1, len(profile.styles) + len(profile.grooves))
    if tag_style:
        ts = tag_style.lower()
        for s in profile.styles:
            if s == ts or s in ts or ts in s:
                hits += 1
    if tag_groove:
        tg = tag_groove.lower()
        for g in profile.grooves:
            if g == tg or g in tg or tg in g:
                hits += 1
    return hits / total


def _mood_score(haystack: str, profile: VibeProfile) -> float:
    if not profile.mood_tokens:
        return 0.0
    hs = haystack.lower()
    hits = sum(1 for t in profile.mood_tokens if len(t) > 1 and t in hs)
    return min(1.0, hits / 4.0)


# Weights chosen empirically — BPM and energy dominate, style provides
# disambiguation, mood is a tiebreaker.
_W_BPM = 3.0
_W_ENERGY = 2.5
_W_STYLE = 2.0
_W_MOOD = 1.0
_W_TOTAL = _W_BPM + _W_ENERGY + _W_STYLE + _W_MOOD


@dataclass
class ScoredCatalogSong:
    song: Song
    tags: Optional[SongTag]
    score: float
    matched: dict


def score_catalog(
    rows: Iterable[tuple[Song, Optional[SongTag]]],
    profile: VibeProfile,
) -> list[ScoredCatalogSong]:
    """Score every catalog song against the profile. Empty profile → all 0.5."""
    out: list[ScoredCatalogSong] = []
    for song, tags in rows:
        bpm = float(tags.bpm) if (tags and tags.bpm) else None
        bpm_s = _bpm_score(bpm, profile)
        energy_s = _energy_score(tags.energy if tags else None, profile.energy)
        style_s = _style_score(tags.style if tags else None, tags.groove_tag if tags else None, profile)
        hay = " ".join(filter(None, [song.title, song.artist, tags.style if tags else None,
                                     tags.groove_tag if tags else None,
                                     tags.era_tag if tags else None]))
        mood_s = _mood_score(hay, profile)

        raw = (_W_BPM * bpm_s + _W_ENERGY * energy_s
               + _W_STYLE * style_s + _W_MOOD * mood_s)

        # Empty-query fallback: surface tagged songs first.
        if profile.is_empty:
            raw = 0.3 + (0.2 if tags else 0.0)

        out.append(ScoredCatalogSong(
            song=song, tags=tags, score=raw,
            matched={
                "bpm": round(bpm_s, 2),
                "energy": round(energy_s, 2),
                "style": round(style_s, 2),
                "mood": round(mood_s, 2),
            },
        ))
    out.sort(key=lambda x: x.score, reverse=True)
    return out


# ───────────────────── Public API ───────────────────── #

def search(
    db: Session,
    *,
    user_id: Optional[int],
    query: str,
    top_k: int = 12,
) -> dict:
    """Run the full vibe search → Spotify-shaped result dict."""
    profile = parse_intent(query)

    rows = (
        db.query(Song, SongTag)
        .outerjoin(SongTag, SongTag.song_id == Song.id)
        .all()
    )
    scored = score_catalog(rows, profile)

    # Drop zero-score noise unless the query was empty.
    if not profile.is_empty:
        scored = [s for s in scored if s.score > 0.05]

    scored = scored[:max(1, top_k)]

    # Library membership for current user.
    in_lib_ids: set[int] = set()
    if user_id is not None and scored:
        ids = [s.song.id for s in scored]
        rows2 = (
            db.query(LibrarySong.song_id)
            .filter(LibrarySong.user_id == user_id, LibrarySong.song_id.in_(ids))
            .all()
        )
        in_lib_ids = {r[0] for r in rows2 if r[0] is not None}

    # Max-score for percentage normalisation. Falls back to theoretical max.
    max_score = max((s.score for s in scored), default=1.0) or 1.0
    theoretical_max = _W_TOTAL  # all kernels = 1
    norm_max = max(max_score, theoretical_max * 0.5)

    songs_out = []
    for s in scored:
        pct = round(min(100.0, (s.score / norm_max) * 100.0), 1)
        songs_out.append({
            "title": s.song.title,
            "artist": s.song.artist,
            "source": "catalog",
            "in_library": s.song.id in in_lib_ids,
            "match_percentage": pct,
            "song_id": s.song.id,
            "style": s.tags.style if s.tags else None,
            "energy": s.tags.energy if s.tags else None,
            "spotify_id": None,
            "preview_url": s.song.audio_url,
            "album_art": None,
            "spotify_url": None,
        })

    return {
        "query": query,
        "vibe_description": _describe(profile),
        "search_query": query,
        "genres": profile.styles or profile.grooves,
        "songs": songs_out,
    }


def _describe(p: VibeProfile) -> str:
    parts: list[str] = []
    if p.bpm_center:
        parts.append(f"≈{int(p.bpm_center)} BPM")
    if p.energy:
        parts.append({"low": "舒缓低能量", "medium": "中等律动", "high": "高能炸场"}[p.energy])
    if p.styles:
        parts.append("/".join(p.styles))
    if p.grooves:
        parts.append("/".join(p.grooves))
    if p.era_hint:
        parts.append(p.era_hint)
    return " · ".join(parts) if parts else "无明确意图，返回热门候选"
