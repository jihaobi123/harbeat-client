"""Normalize external genre/style/tag labels into stable snake_case tokens."""
from __future__ import annotations

import re
import unicodedata

_ALIASES = {
    "hip hop": "hiphop",
    "hip-hop": "hiphop",
    "rap": "hiphop",
    "old school hip hop": "hiphop_oldschool",
    "old school hip-hop": "hiphop_oldschool",
    "old skool": "old_school",
    "old school": "old_school",
    "funky": "funk",
    "funk / soul": "funk",
    "electro funk": "electro_funk",
    "electro-funk": "electro_funk",
    "boogie funk": "boogie",
    "g funk": "g_funk",
    "g-funk": "g_funk",
    "r&b": "rnb",
    "r and b": "rnb",
    "rnb": "rnb",
    "rhythm and blues": "rnb",
    "drum n bass": "drum_and_bass",
    "drum and bass": "drum_and_bass",
    "b-boy": "bboy",
    "b boy": "bboy",
    "4/4": "four_on_floor",
}


def normalize_label(label: object) -> str:
    raw = str(label or "").strip().lower()
    if not raw:
        return ""
    raw = unicodedata.normalize("NFKD", raw)
    raw = raw.replace("&", " and ")
    raw = re.sub(r"[/+]", " ", raw)
    raw = re.sub(r"[^a-z0-9\s-]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if raw in _ALIASES:
        return _ALIASES[raw]
    raw = raw.replace("-", " ")
    if raw in _ALIASES:
        return _ALIASES[raw]
    return re.sub(r"\s+", "_", raw)


def normalize_labels(labels: list[object] | tuple[object, ...] | set[object]) -> list[str]:
    out: list[str] = []
    for label in labels or []:
        norm = normalize_label(label)
        if norm and norm not in out:
            out.append(norm)
    return out
