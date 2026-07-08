"""Normalize external genre/style/tag labels into stable snake_case tokens."""
from __future__ import annotations

import re
import unicodedata

_ALIASES = {
    "hip hop": "hiphop",
    "hip-hop": "hiphop",
    "rap": "hiphop",
    "hiphop": "hiphop",
    "hip-hop/rap": "hiphop",
    "hip-hop rap": "hiphop",
    "hip hop rap": "hiphop",
    "r and b soul": "rnb",
    "old school hip hop": "hiphop_oldschool",
    "old school hip-hop": "hiphop_oldschool",
    "old-school hip-hop": "hiphop_oldschool",
    "old-school hip hop": "hiphop_oldschool",
    "old skool": "old_school",
    "old school": "old_school",
    "boom bap": "boom_bap",
    "boom-bap": "boom_bap",
    "pop rap": "pop_rap",
    "pop-rap": "pop_rap",
    "west coast hip hop": "west_coast",
    "west coast hip-hop": "west_coast",
    "east coast hip hop": "east_coast",
    "east coast hip-hop": "east_coast",
    "battle rap": "battle_rap",
    "battle-rap": "battle_rap",
    "aggressive hip hop": "aggressive_hiphop",
    "aggressive hip-hop": "aggressive_hiphop",
    "trap soul": "trap_soul",
    "trap-soul": "trap_soul",
    "funky": "funk",
    "funk / soul": "funk",
    "funk soul": "funk",
    "electro funk": "electro_funk",
    "electro-funk": "electro_funk",
    "synth funk": "synth_funk",
    "synth-funk": "synth_funk",
    "boogie funk": "boogie",
    "g funk": "g_funk",
    "g-funk": "g_funk",
    "jazz funk": "jazz_funk",
    "jazz-funk": "jazz_funk",
    "latin funk": "latin_funk",
    "latin-funk": "latin_funk",
    "r&b": "rnb",
    "r and b": "rnb",
    "rnb": "rnb",
    "rhythm and blues": "rnb",
    "contemporary r b": "rnb",
    "contemporary r and b": "rnb",
    "drum n bass": "drum_and_bass",
    "drum and bass": "drum_and_bass",
    "drum breaks": "drum_breaks",
    "drum break": "drum_breaks",
    "b-boy": "bboy",
    "b boy": "bboy",
    "break beat": "breakbeat",
    "break-beat": "breakbeat",
    "breakbeats": "breakbeat",
    "breaks": "breakbeat",
    "deep house": "deep_house",
    "deep-house": "deep_house",
    "garage house": "garage_house",
    "garage-house": "garage_house",
    "jackin house": "jackin_house",
    "jackin' house": "jackin_house",
    "soulful house": "soulful_house",
    "soulful-house": "soulful_house",
    "vocal house": "vocal_house",
    "vocal-house": "vocal_house",
    "4/4": "four_on_floor",
    "four on the floor": "four_on_floor",
    "four-on-the-floor": "four_on_floor",
    "heavy bass": "heavy_bass",
    "heavy-bass": "heavy_bass",
    "hard hitting": "hard_hitting",
    "hard-hitting": "hard_hitting",
    "street dance": "street",
    "street-dance": "street",
    "dance practice": "practice",
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
