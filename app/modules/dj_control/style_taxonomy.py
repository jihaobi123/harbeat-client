"""Dance-style tag taxonomy used by external metadata scoring."""
from __future__ import annotations

STYLE_TAG_PROFILE: dict[str, dict[str, list[str]]] = {
    "popping": {
        "strong": ["funk", "electro", "boogie", "electro_funk", "g_funk"],
        "medium": ["hiphop_oldschool", "synth_funk", "groovy", "west_coast", "east_coast", "robotic", "street"],
        "negative": ["ambient", "acoustic", "ballad"],
    },
    "locking": {
        "strong": ["funk", "soul", "disco", "jazz_funk", "boogie"],
        "medium": ["groovy", "dance", "old_school", "bright", "upbeat"],
        "negative": ["trap", "ambient", "ballad"],
    },
    "breaking": {
        "strong": ["breakbeat", "hiphop_oldschool", "funk", "boom_bap", "bboy", "old_school"],
        "medium": ["electro", "latin_funk", "drum_breaks", "raw", "street", "battle_rap"],
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
        "strong": ["krump", "trap", "aggressive_hiphop", "battle_rap", "hard_hitting"],
        "medium": ["dark", "heavy_bass", "urban", "street"],
        "negative": ["soft_pop", "acoustic", "ambient"],
    },
    "hiphop": {
        "strong": ["hiphop", "boom_bap", "rap", "rnb", "trap_soul", "hiphop_oldschool"],
        "medium": ["urban", "groovy", "pop_rap", "old_school", "street", "west_coast", "east_coast", "battle_rap", "trap"],
        "negative": ["ambient", "classical"],
    },
    "jazz": {
        "strong": ["jazz", "swing", "electro_swing", "jazz_pop", "big_band", "jump_blues"],
        "medium": ["latin_jazz", "soul_jazz", "shuffle", "brass", "walking_bass", "groovy"],
        "negative": ["trap", "ambient", "minimal"],
    },
}
