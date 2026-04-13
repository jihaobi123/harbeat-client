"""Vibe interpretation: natural language → structured search hints.

Adapted from FinalReco/services/vibe_service.py — no external dependencies.
"""
from __future__ import annotations

from typing import Dict, List


TRANSLATION_HINTS: Dict[str, str] = {
    "雨夜": "rainy midnight atmosphere",
    "忧郁": "melancholic introspective mood",
    "伤感": "sad reflective feeling",
    "霓虹": "neon city glow",
    "独自": "solitary and intimate",
    "漫步": "slow drifting motion",
    "驾驶": "night driving pulse",
    "老派": "old school character",
    "爵士": "jazz-influenced harmony",
    "嘻哈": "hip-hop groove",
    "复古": "retro vintage warmth",
    "黑夜": "dark nocturnal energy",
    "迷幻": "psychedelic dreamy soundscape",
    "街舞": "street dance groove",
    "派对": "party high energy celebration",
    "放松": "relaxed chill easy listening",
    "热血": "intense powerful energetic",
    "慵懒": "lazy laid-back afternoon",
}

GENRE_KEYWORDS: Dict[str, List[str]] = {
    "hip-hop": ["hip hop", "hip-hop", "hiphop", "rap", "boom bap", "old school", "嘻哈", "说唱"],
    "jazz": ["jazz", "jazzhop", "爵士", "sax"],
    "electronic": ["electronic", "synth", "edm", "neon", "赛博", "电子"],
    "ambient": ["ambient", "atmospheric", "drone", "rainy", "雨夜"],
    "rock": ["rock", "guitar", "band", "alt rock", "摇滚"],
    "indie": ["indie", "lofi", "lo-fi", "bedroom", "独立"],
    "acoustic": ["acoustic", "unplugged", "folk", "singer-songwriter", "民谣"],
    "soul": ["soul", "r&b", "rnb", "motown", "灵魂"],
    "pop": ["pop", "radio", "mainstream", "流行"],
    "trap": ["trap", "bass", "808"],
    "funk": ["funk", "funky", "groove", "放克"],
    "reggae": ["reggae", "dancehall", "雷鬼"],
    "latin": ["latin", "salsa", "reggaeton", "拉丁"],
    "kpop": ["kpop", "k-pop", "韩流", "韩国"],
}


def _extract_genres(text: str) -> List[str]:
    lowered = text.lower()
    scored = []
    for genre, keys in GENRE_KEYWORDS.items():
        score = sum(1 for key in keys if key in lowered)
        if score > 0:
            scored.append((score, genre))
    scored.sort(reverse=True)
    genres = [genre for _, genre in scored[:2]]
    return genres


def _build_vibe_description(text: str) -> str:
    hints = [value for key, value in TRANSLATION_HINTS.items() if key in text]
    base = text.strip()
    if hints:
        return f"{base}. Vibe cues: {', '.join(hints)}."
    return base


def _extract_year_filter(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["90s", "1990", "199", "九十"]):
        return "year:1990-2005"
    if any(token in lowered for token in ["80s", "1980", "198", "八十"]):
        return "year:1980-1995"
    if any(token in lowered for token in ["2000s", "2000", "千禧"]):
        return "year:2000-2015"
    return ""


def interpret_vibe(text: str) -> dict:
    """Parse a vibe description into structured search hints."""
    genres = _extract_genres(text)
    vibe_description = _build_vibe_description(text)
    year_filter = _extract_year_filter(text)
    # Use original text as primary search — more reliable with Spotify API
    parts = [text.strip()]
    if year_filter:
        parts.append(year_filter)
    search_query = " ".join(parts)
    return {
        "genres": genres,
        "vibe_description": vibe_description,
        "search_query": search_query,
        "original_text": text.strip(),
    }
