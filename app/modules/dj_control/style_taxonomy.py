"""Dance-style tag taxonomy used by external metadata scoring."""
from __future__ import annotations

STYLE_TAG_PROFILE: dict[str, dict[str, list[str]]] = {
    "popping": {
        "strong": ["funk", "electro", "boogie", "electro_funk", "g_funk"],
        "medium": ["hiphop_oldschool", "synth_funk", "groovy", "west_coast", "robotic"],
        "negative": ["ambient", "acoustic", "ballad"],
    },
    "locking": {
        "strong": ["funk", "soul", "disco", "jazz_funk"],
        "medium": ["groovy", "dance", "old_school", "bright", "upbeat"],
        "negative": ["trap", "ambient", "ballad"],
    },
    "breaking": {
        "strong": ["breakbeat", "hiphop_oldschool", "funk", "boom_bap", "bboy"],
        "medium": ["electro", "latin_funk", "drum_breaks", "raw"],
        "negative": ["ambient", "ballad", "acoustic"],
    },
    "house": {
        "strong": ["house", "deep_house", "garage_house", "jackin_house"],
        "medium": ["dance", "club", "percussive", "soulful_house", "four_on_floor"],
        "negative": ["ballad", "ambient"],
    },
    "waacking": {
        "strong": ["disco", "funk", "soul", "vocal_house"],
        "medium": ["dance", "glamorous", "dramatic", "bright", "diva_vocal"],
        "negative": ["trap", "ambient", "minimal"],
    },
    "krump": {
        "strong": ["krump", "trap", "aggressive_hiphop", "battle_rap"],
        "medium": ["dark", "heavy_bass", "hard_hitting", "urban"],
        "negative": ["soft_pop", "acoustic", "ambient"],
    },
    "hiphop": {
        "strong": ["hiphop", "boom_bap", "rap", "rnb", "trap_soul"],
        "medium": ["urban", "groovy", "pop_rap", "old_school", "street"],
        "negative": ["ambient", "classical"],
    },
}

