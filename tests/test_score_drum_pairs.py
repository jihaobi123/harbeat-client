from __future__ import annotations

import pytest

from scripts.score_drum_pairs import generate_pair_rows


def _analysis() -> dict:
    return {
        "version": "drum_transcription_consensus_v4",
        "status": "ready",
        "needs_review": False,
        "counts": {
            "kick": 4,
            "snare": 2,
            "hihat": 8,
            "bass_808": 4,
            "percussion": 2,
        },
        "pattern": {
            "resolution": 16,
            "bars_analyzed": 8,
            "dominant": {
                "kick": "K...K...K...K...",
                "snare": "....S.......S...",
                "hihat": "H.H.H.H.H.H.H.H.",
                "bass_808": "B...B...B...B...",
                "percussion": "........P.......",
            },
        },
    }


def test_generate_all_unordered_pairs() -> None:
    songs = {"c": _analysis(), "a": _analysis(), "b": _analysis()}

    rows = generate_pair_rows(songs)

    assert [(row["song_a_id"], row["song_b_id"]) for row in rows] == [
        ("a", "b"),
        ("a", "c"),
        ("b", "c"),
    ]
    assert all(row["score"] == 1.0 for row in rows)
    assert all(row["human_band"] is None for row in rows)


def test_unknown_song_in_selected_pair_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown song_id"):
        generate_pair_rows({"a": _analysis(), "b": _analysis()}, [("a", "missing")])
