from types import SimpleNamespace

from app.modules.dj_control.cut_strategy import prepare_live_pool


def song(song_id: str, energy: float, style_score: float = 0.7):
    return SimpleNamespace(
        id=song_id,
        title=song_id,
        artist="Artist",
        energy=energy / 100.0,
        bpm=100.0,
        duration=180.0,
        beat_points=[],
        downbeats=[],
        phrase_map=[],
        cue_points=[],
        transition_windows=[],
        intro_clean_score=0.5,
        vocal_events=[],
        bass_risk_windows=[],
        stems={},
        dance_style_scores={"popping": style_score},
        energy_curve=[],
    )


def test_prepare_live_pool_groups_reserve_by_bucket_and_sync_priority():
    active = [song("a", 62), song("b", 74), song("c", 55), song("d", 45)]
    library = [
        *active,
        song("r40", 42),
        song("r50", 56),
        song("r80", 84, 0.9),
        song("r80b", 86, 0.4),
        song("blocked", 84, 1.0),
    ]

    result = prepare_live_pool(
        active_queue=active,
        library_songs=library,
        style="popping",
        target_reserve_per_bucket=1,
        include_buckets=["40-50", "50-60", "80-90"],
        exclude_song_ids={"blocked"},
    )

    assert result["active_queue"] == ["a", "b", "c", "d"]
    assert result["reserve_pool"]["40-50"] == ["r40"]
    assert result["reserve_pool"]["50-60"] == ["r50"]
    assert result["reserve_pool"]["80-90"] == ["r80"]
    assert "blocked" not in result["reserve_pool"]["80-90"]
    assert result["sync_priority"]["p0"] == ["a"]
    assert result["sync_priority"]["p1"] == ["b"]
    assert result["sync_priority"]["p2"] == ["c", "d"]
    assert set(result["sync_priority"]["p3"]) == {"r40", "r50", "r80"}
    assert result["energy_profiles"]["r80"]["bucket"] == "80-90"
