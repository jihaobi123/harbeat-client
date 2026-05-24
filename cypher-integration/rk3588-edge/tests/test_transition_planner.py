import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "audio-engine"))

from transition_planner import build_pair_matrix, plan_mix  # noqa: E402


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


def _batch_song(song_id, *, bpm, camelot, vocals, bass, drums=0.8, label="Chorus", energy=0.7):
    return {
        "song_id": song_id,
        "title": song_id.upper(),
        "bpm": bpm,
        "camelot": camelot,
        "energy": energy,
        "duration": 210.0,
        "has_stems": True,
        "files": {
            "original": {"url": f"http://jetson/{song_id}.wav", "size": 100, "sha256": "a" * 64, "format": "wav"},
            "stems": {
                "vocals": {"url": f"http://jetson/{song_id}/vocals.wav", "size": 10, "sha256": "b" * 64, "format": "wav"},
                "drums": {"url": f"http://jetson/{song_id}/drums.wav", "size": 10, "sha256": "c" * 64, "format": "wav"},
                "bass": {"url": f"http://jetson/{song_id}/bass.wav", "size": 10, "sha256": "d" * 64, "format": "wav"},
                "other": {"url": f"http://jetson/{song_id}/other.wav", "size": 10, "sha256": "e" * 64, "format": "wav"},
            },
        },
        "sections": [
            {
                "start": 24.0,
                "end": 48.0,
                "label": "Intro",
                "stem_activity": {"vocals": 0.1, "drums": drums, "bass": bass, "other": 0.6},
            },
            {
                "start": 150.0,
                "end": 176.0,
                "label": label,
                "stem_activity": {"vocals": vocals, "drums": drums, "bass": bass, "other": 0.8},
            },
        ],
        "beats": [24.0 + i * (60.0 / bpm) for i in range(80)],
    }


def test_build_pair_matrix_tags_every_ordered_pair_and_marks_fallback_without_stems():
    songs = [
        _batch_song("a", bpm=93.0, camelot=4, vocals=0.95, bass=0.9),
        _batch_song("b", bpm=83.0, camelot=10, vocals=0.92, bass=0.85),
        _batch_song("c", bpm=124.0, camelot=5, vocals=0.05, bass=0.25, label="Instrumental"),
    ]
    songs[1]["files"]["stems"].pop("bass")

    matrix = build_pair_matrix(songs, stems_available=True)

    assert len(matrix) == 6
    ab = next(item for item in matrix if item["from_song"] == "a" and item["to_song"] == "b")
    assert ab["playback_tier"] == "non_stem"
    assert ab["fallback_style"] == ab["style"]
    assert "non_stem_fallback" in ab["tags"]
    assert "key_tense" in ab["tags"]
    assert 0.0 <= ab["confidence"] <= 1.0


def test_plan_mix_reorders_playlist_by_pair_scores_and_embeds_transition_tags():
    songs = [
        _batch_song("a", bpm=93.0, camelot=4, vocals=0.95, bass=0.9),
        _batch_song("b", bpm=124.0, camelot=5, vocals=0.05, bass=0.25, label="Instrumental"),
        _batch_song("c", bpm=83.0, camelot=11, vocals=0.95, bass=0.9),
    ]

    plan = plan_mix(songs, stems_available=True, optimize_order=True)

    assert plan["pair_matrix_summary"]["pairs_evaluated"] == 6
    assert plan["tracks"][0]["song_id"] == "a"
    assert plan["tracks"][1]["song_id"] == "b"
    transition = plan["transitions"][0]
    assert transition["playback_tier"] == "stem_aware"
    assert transition["confidence"] > 0
    assert transition["fallback_style"]
    assert isinstance(transition["tags"], list)
