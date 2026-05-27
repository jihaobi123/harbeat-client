"""Vibe Search — free-form text description → ranked songs.

The DJ Control "Vibe" mode lets the user type something like
"深夜地下 cypher 阴暗 boom bap 95bpm" and get back library songs that
best match the description.

Scoring is a lightweight bag-of-words over the song's text surface
(title + artist) and the catalog SongTag fields (style / energy / vocal_type
/ era_tag / groove_tag), with a few bonus heuristics:

* BPM hint — numeric tokens in the query (e.g. "95", "120bpm") are matched
  against ``LibrarySong.bpm`` with a triangular kernel (±15 bpm).
* Energy hint — keywords like "chill / 慢 / 低能量 / relax" map to *low*
  energy and "hype / 燥 / 嗨 / peak / 激烈 / 快" map to *high* energy; we
  add a bonus when ``LibrarySong.energy`` matches.
* Optional ``fill_duration`` greedily walks the ranked list until the sum
  of ``LibrarySong.duration`` reaches ``target_duration_sec``.

This intentionally avoids embeddings / external services so it works
offline on the deployment box.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.library.models import LibrarySong


# ── Lexicons ────────────────────────────────────────────────────────────── #

LOW_ENERGY_HINTS = {
    # english
    "chill", "calm", "relax", "relaxed", "smooth", "mellow", "soft", "slow",
    "ambient", "lo-fi", "lofi", "downtempo", "quiet", "warm",
    # chinese
    "平静", "舒缓", "安静", "慢", "低能量", "放松", "柔和", "暖", "深夜", "夜晚",
    "暗", "阴", "冷",
}
HIGH_ENERGY_HINTS = {
    # english
    "hype", "peak", "wild", "energetic", "high", "fast", "banger", "explosive",
    "intense", "aggressive", "rave", "heat", "fire", "drop", "hard",
    # chinese
    "嗨", "燥", "狂", "炸", "热", "激烈", "高能量", "快", "猛", "冲", "顶峰",
    "爆炸",
}

# Stopwords we strip out before tokenisation; keep it small.
STOPWORDS = {"a", "an", "the", "and", "or", "of", "to", "in", "on", "for",
             "with", "is", "are", "be", "by", "at", "feat", "ft", "vs", "x"}


# ── Tokenisation ────────────────────────────────────────────────────────── #

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9][a-zA-Z0-9'\-]*")
_BPM_RE = re.compile(r"(\d{2,3})\s*(?:bpm|拍|每分)?", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    """English word tokens + each CJK char as one token."""
    if not text:
        return []
    raw = _TOKEN_RE.findall(text.lower())
    return [t for t in raw if t and t not in STOPWORDS]


def _extract_bpm_hints(text: str) -> list[int]:
    hits = []
    for m in _BPM_RE.finditer(text):
        try:
            v = int(m.group(1))
        except ValueError:
            continue
        if 50 <= v <= 220:
            hits.append(v)
    return hits


def _has_any(tokens: set[str], lex: set[str]) -> bool:
    return any(t in lex for t in tokens)


# ── Scoring ─────────────────────────────────────────────────────────────── #

@dataclass
class VibeMatch:
    song: LibrarySong
    score: float
    matched: list[str]


def _song_surface(song: LibrarySong) -> tuple[str, dict[str, str]]:
    """Return (joined searchable text, per-field map for matched diagnostics)."""
    tag = None
    catalog = getattr(song, "song", None)
    if catalog is not None:
        tag = getattr(catalog, "tags", None)

    fields: dict[str, str] = {
        "title": song.title or "",
        "artist": song.artist or "",
        "style": (tag.style if tag else None) or "",
        "energy_tag": (tag.energy if tag else None) or "",
        "vocal_type": (tag.vocal_type if tag else None) or "",
        "era_tag": (tag.era_tag if tag else None) or "",
        "groove_tag": (tag.groove_tag if tag else None) or "",
    }
    return " ".join(fields.values()).lower(), fields


def _bpm_bonus(song_bpm: float | None, hints: list[int]) -> float:
    if not song_bpm or not hints:
        return 0.0
    best = max(0.0, 1.0 - min(abs(song_bpm - h) for h in hints) / 15.0)
    return best * 2.0  # up to +2 when bpm hits


def _energy_bonus(song_energy: float | None, low: bool, high: bool) -> float:
    if song_energy is None or (not low and not high):
        return 0.0
    if low and song_energy <= 0.45:
        return 1.0 + (0.45 - song_energy) * 1.5
    if high and song_energy >= 0.6:
        return 1.0 + (song_energy - 0.6) * 1.5
    return 0.0


def score_songs(songs: list[LibrarySong], query: str) -> list[VibeMatch]:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    q_set = set(q_tokens)
    bpm_hints = _extract_bpm_hints(query)
    want_low = _has_any(q_set, LOW_ENERGY_HINTS)
    want_high = _has_any(q_set, HIGH_ENERGY_HINTS)

    out: list[VibeMatch] = []
    for song in songs:
        text, fields = _song_surface(song)
        if not text.strip():
            continue
        matched: list[str] = []
        score = 0.0
        for tok in q_set:
            if not tok or tok in LOW_ENERGY_HINTS or tok in HIGH_ENERGY_HINTS:
                continue  # already credited via energy bonus
            if tok in text:
                matched.append(tok)
                # weight: tag hits > artist > title (tag richest signal)
                if any(tok in fields[k].lower() for k in ("style", "energy_tag",
                       "vocal_type", "era_tag", "groove_tag")):
                    score += 1.5
                elif tok in fields["artist"].lower():
                    score += 1.0
                else:
                    score += 0.8

        score += _bpm_bonus(song.bpm, bpm_hints)
        score += _energy_bonus(song.energy, want_low, want_high)

        if score > 0:
            out.append(VibeMatch(song=song, score=score, matched=matched))

    out.sort(key=lambda m: (-m.score, -(m.song.bpm or 0)))
    return out


def fill_to_duration(matches: list[VibeMatch], target_sec: float) -> list[VibeMatch]:
    """Greedy: walk ranked list; stop once cumulative duration ≥ target."""
    if target_sec <= 0:
        return matches
    out: list[VibeMatch] = []
    acc = 0.0
    for m in matches:
        out.append(m)
        acc += float(m.song.duration or 0)
        if acc >= target_sec:
            break
    return out
