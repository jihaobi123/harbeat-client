import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "audio-engine"))

from transition_planner import plan_mix  # noqa: E402


def test_vocal_handoff_transition_includes_beat_aligned_dynamic_ratio():
    songs = [
        {
            "song_id": "a",
            "title": "A",
            "bpm": 93.0,
            "camelot": 4,
            "energy": 0.7,
            "duration": 210.0,
            "sections": [
                {
                    "start": 140.0,
                    "end": 170.0,
                    "label": "Chorus",
                    "stem_activity": {"vocals": 1.0, "drums": 0.9, "bass": 0.9, "other": 0.8},
                }
            ],
        },
        {
            "song_id": "b",
            "title": "B",
            "bpm": 83.3,
            "camelot": 5,
            "energy": 0.68,
            "duration": 250.0,
            "beats": [32.16, 32.88, 33.60, 34.32, 35.04, 35.76, 36.48, 37.20, 37.92, 38.64, 39.36, 40.08, 40.80, 41.52, 42.24],
            "sections": [
                {
                    "start": 32.16,
                    "end": 54.0,
                    "label": "Verse",
                    "stem_activity": {"vocals": 0.96, "drums": 0.72, "bass": 0.70, "other": 0.65},
                }
            ],
        },
    ]

    plan = plan_mix(
        songs,
        stems_available=True,
        prefer_exits={"a": 144.615},
        prefer_entries={"b": 32.16},
    )

    transition = plan["transitions"][0]

    assert transition["style"] == "vocal_handoff"
    assert 0.32 <= transition["vocal_handoff_ratio"] <= 0.62
    assert transition["vocal_handoff_ratio"] != 0.45
