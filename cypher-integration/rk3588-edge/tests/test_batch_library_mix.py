import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "audio-engine" / "scripts"))

from batch_library_mix import build_batch_report, normalize_jetson_song  # noqa: E402


def test_normalize_jetson_song_adds_stream_manifest_and_numeric_features():
    song = normalize_jetson_song(
        {
            "id": 100,
            "title": "Good Times",
            "artist": "Esone",
            "audio_url": "/home/mark/file.mp3",
            "duration": 180,
            "bpm": 121,
            "energy": "high",
            "camelot_key": "4A",
            "tags": ["hiphop"],
        },
        jetson_base_url="http://jetson:8000",
    )

    assert song["song_id"] == "100"
    assert song["energy"] == 0.78
    assert song["camelot"] == 4
    assert song["files"]["original"]["url"] == "http://jetson:8000/api/stream/100"
    assert set(song["files"]["stems"]) == {"vocals", "drums", "bass", "other"}


def test_build_batch_report_contains_tracks_pair_matrix_and_mix_plan():
    songs = [
        normalize_jetson_song({"id": 1, "title": "A", "artist": "AA", "audio_url": "x", "duration": 180, "bpm": 93, "energy": "medium"}),
        normalize_jetson_song({"id": 2, "title": "B", "artist": "BB", "audio_url": "x", "duration": 180, "bpm": 95, "energy": "medium"}),
        normalize_jetson_song({"id": 3, "title": "C", "artist": "CC", "audio_url": "x", "duration": 180, "bpm": 120, "energy": "high"}),
    ]

    report = build_batch_report(songs, optimize_order=True)

    assert len(report["tracks"]) == 3
    assert len(report["pair_matrix"]) == 6
    assert report["mix_plan"]["transitions"]
    assert report["pair_matrix_summary"]["pairs_evaluated"] == 6
