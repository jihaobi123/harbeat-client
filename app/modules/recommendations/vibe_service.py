"""Vibe interpretation: natural language → structured search hints.

Ported from FinalReco/services/vibe_service.py (commit 1d65a9dc).
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
    "放松": "relaxed chill atmosphere",
    "慵懒": "lazy laid-back mood",
    "热血": "energetic battle-ready intensity",
    "派对": "party celebration energy",
    "街舞": "street dance groove",
    "深夜": "late night solitude",
}

GENRE_KEYWORDS: Dict[str, List[str]] = {
    "hip-hop": ["hip hop", "hip-hop", "hiphop", "rap", "boom bap", "old school", "嘻哈"],
    "jazz": ["jazz", "jazzhop", "爵士", "sax"],
    "electronic": ["electronic", "synth", "edm", "neon", "赛博"],
    "ambient": ["ambient", "atmospheric", "drone", "rainy", "雨夜"],
    "rock": ["rock", "guitar", "band", "alt rock"],
    "indie": ["indie", "lofi", "lo-fi", "bedroom"],
    "acoustic": ["acoustic", "unplugged", "folk", "singer-songwriter"],
    "soul": ["soul", "r&b", "rnb", "motown", "灵魂"],
    "pop": ["pop", "radio", "mainstream", "流行"],
    "trap": ["trap", "bass", "808"],
    "funk": ["funk", "funky", "groove", "放克"],
    "reggae": ["reggae", "dancehall", "雷鬼"],
    "latin": ["latin", "salsa", "reggaeton", "拉丁"],
    "kpop": ["kpop", "k-pop", "韩流", "韩国"],
}


def _extract_year_filter(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["90s", "1990", "199", "九十"]):
        return "year:1990-2005"
    if any(token in lowered for token in ["80s", "1980", "198", "八十"]):
        return "year:1980-1995"
    if any(token in lowered for token in ["2000s", "2000", "千禧"]):
        return "year:2000-2015"
    return ""


def _extract_genres(text: str) -> List[str]:
    lowered = text.lower()
    scored = []
    for genre, keys in GENRE_KEYWORDS.items():
        score = sum(1 for key in keys if key in lowered)
        if score > 0:
            scored.append((score, genre))
    scored.sort(reverse=True)
    genres = [genre for _, genre in scored[:2]]
    return genres or ["electronic"]


def _build_vibe_description(text: str) -> str:
    hints = [value for key, value in TRANSLATION_HINTS.items() if key in text]
    base = text.strip()
    if hints:
        return f"{base}. Vibe cues: {', '.join(hints)}."
    return base


# Map Chinese dance/mood keywords to English search terms
_SEARCH_HINTS: Dict[str, str] = {
    "炸场": "hype battle",
    "高能量": "high energy",
    "低沉": "dark bass heavy",
    "有力": "powerful hard",
    "轻松": "chill easy",
    "华丽": "dramatic glamorous",
    "机械感": "robotic mechanical",
    "抒情": "emotional soulful",
    "慢歌": "slow ballad",
    "律动": "groovy bounce",
    "popping": "funk popping",
    "waacking": "disco waacking",
    "locking": "funk locking",
    "breaking": "breakbeat bboy",
    "house": "house dance",
    "battle": "battle hype",
}


def _build_search_query(text: str, genres: List[str]) -> str:
    """Build a Spotify search query from user text + detected genres."""
    lowered = text.lower()
    parts: List[str] = []

    # Add English search hints for Chinese terms
    for cn, en in _SEARCH_HINTS.items():
        if cn in lowered:
            parts.append(en)

    # Add genre as a keyword (not genre: filter)
    if genres:
        parts.append(genres[0])

    # Keep any English words from the original query
    for word in text.split():
        if word.isascii() and len(word) > 1 and word.lower() not in ("the", "a", "an", "and", "or"):
            parts.append(word.lower())

    # Add translated vibe hints
    for key, val in TRANSLATION_HINTS.items():
        if key in text:
            # Take first 2 words of English translation
            parts.append(" ".join(val.split()[:2]))

    # Year filter
    year = _extract_year_filter(text)
    if year:
        parts.append(year)

    # Deduplicate while preserving order
    seen = set()
    unique: List[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return " ".join(unique[:6]) if unique else "dance music"


def interpret_vibe(text: str) -> dict:
    """Parse a vibe description into structured search hints."""
    genres = _extract_genres(text)
    vibe_description = _build_vibe_description(text)
    search_query = _build_search_query(text, genres)
    return {
        "genres": genres,
        "vibe_description": vibe_description,
        "search_query": search_query,
        "original_text": text.strip(),
    }
