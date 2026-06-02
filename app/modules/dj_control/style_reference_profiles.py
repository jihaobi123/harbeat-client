"""Static street-dance reference profiles for style-pick evidence.

These profiles are intentionally small and explainable. They are not a model;
they provide a stable first-stage reference layer that can later be replaced
or augmented by Cyanite/AIMS/self-hosted embeddings without changing
``/api/dj/styles/pick``.
"""
from __future__ import annotations

STYLE_REFERENCE_PROFILES: dict[str, dict] = {
    "breaking": {
        "reference_tags": [
            "breakbeat",
            "funk breaks",
            "b-boy",
            "old school hip-hop",
            "boom bap",
            "electro",
            "drum breaks",
        ],
        "reference_artists": ["The Incredible Bongo Band", "James Brown", "Bambaataa"],
        "description": "Breakbeat, funk breaks, and old-school b-boy records.",
    },
    "hiphop": {
        "reference_tags": [
            "hip hop",
            "hip-hop",
            "boom bap",
            "rap",
            "old school hip-hop",
            "r&b",
            "groove",
        ],
        "reference_artists": ["A Tribe Called Quest", "Dr. Dre", "Missy Elliott"],
        "description": "Groove-forward hip-hop and rap records for freestyle.",
    },
    "popping": {
        "reference_tags": [
            "electro",
            "boogie",
            "funk",
            "electro funk",
            "g-funk",
            "synth funk",
            "robotic",
        ],
        "reference_artists": ["Zapp", "Egyptian Lover", "Parliament"],
        "description": "Electro funk, boogie, and synth-funk oriented popping music.",
    },
    "locking": {
        "reference_tags": [
            "funk",
            "soul",
            "disco",
            "jazz funk",
            "upbeat",
            "funky",
            "old school",
        ],
        "reference_artists": ["James Brown", "Kool & The Gang", "The Meters"],
        "description": "Upbeat funk, soul, and disco records with clear backbeat.",
    },
    "house": {
        "reference_tags": [
            "house",
            "deep house",
            "garage house",
            "jackin house",
            "soulful house",
            "club",
            "4/4",
            "percussive",
        ],
        "reference_artists": ["Masters At Work", "Kerri Chandler", "Armand Van Helden"],
        "description": "Four-on-floor house music with steady club groove.",
    },
    "krump": {
        "reference_tags": [
            "krump",
            "aggressive hip-hop",
            "trap",
            "battle beats",
            "hard rap",
            "dark",
            "heavy bass",
            "high energy",
        ],
        "reference_artists": ["Lil Jon", "Missy Elliott", "Busta Rhymes"],
        "description": "Aggressive battle records with heavy low end and attack.",
    },
    "waacking": {
        "reference_tags": [
            "disco",
            "funk",
            "soul",
            "vocal house",
            "diva vocal",
            "dramatic",
            "glamorous",
            "dance",
            "vocal",
        ],
        "reference_artists": ["Diana Ross", "Sylvester", "Chaka Khan"],
        "description": "Disco, funk, soul, and vocal house with dramatic phrasing.",
    },
}

