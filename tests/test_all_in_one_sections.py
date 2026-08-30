from app.modules.library.analysis import (
    _all_in_one_intro_end,
    _all_in_one_segments_to_phrase_map,
    _generate_dj_hot_cues,
    _start_bar_grid_after_all_in_one_intro,
)


def _segments() -> list[dict]:
    return [
        {"start": 0.0, "end": 0.3, "label": "start"},
        {"start": 0.3, "end": 10.0, "label": "intro"},
        {"start": 10.0, "end": 20.0, "label": "verse"},
        {"start": 20.0, "end": 30.0, "label": "verse"},
        {"start": 30.0, "end": 40.0, "label": "chorus"},
        {"start": 40.0, "end": 42.0, "label": "end"},
    ]


def test_leading_intro_end_comes_only_from_all_in_one_segments() -> None:
    intro_end, metadata = _all_in_one_intro_end(_segments())

    assert intro_end == 10.0
    assert metadata == {
        "intro_detected": True,
        "intro_end": 10.0,
        "origin_reason": "leading_intro_end",
    }


def test_bar_one_is_first_downbeat_after_intro_end() -> None:
    downbeats = [0.2, 2.2, 4.2, 6.2, 8.2, 10.2, 12.2, 14.2]

    product_grid, metadata = _start_bar_grid_after_all_in_one_intro(
        downbeats, _segments(),
    )

    assert product_grid == [10.2, 12.2, 14.2]
    assert metadata["first_bar_downbeat"] == 10.2
    assert metadata["removed_intro_downbeats"] == 5
    assert metadata["intro_end"] == 10.0
    assert metadata["rule"] == "first_downbeat_at_or_after_all_in_one_intro_end"


def test_no_all_in_one_sections_means_no_product_bar_grid() -> None:
    product_grid, metadata = _start_bar_grid_after_all_in_one_intro(
        [0.2, 2.2, 4.2], [],
    )

    assert product_grid == []
    assert metadata["status"] == "all_in_one_sections_unavailable"


def test_bar_grid_counts_meter_from_anchor_instead_of_copying_mid_song_errors() -> None:
    beats = [round(0.2 + index * 0.5, 3) for index in range(40)]
    noisy_downbeats = [0.2, 2.2, 4.2, 6.2, 8.2, 10.2, 11.2, 14.2, 18.2]

    product_grid, metadata = _start_bar_grid_after_all_in_one_intro(
        noisy_downbeats,
        _segments(),
        beat_times=beats,
        beats_per_bar=4,
    )

    assert product_grid[:5] == [10.2, 12.2, 14.2, 16.2, 18.2]
    assert metadata["grid_mode"] == "counted_beats_from_first_post_intro_downbeat"
    assert metadata["beats_per_bar"] == 4


def test_phrase_map_preserves_adjacent_same_label_boundaries() -> None:
    phrase_map = _all_in_one_segments_to_phrase_map(
        _segments(), [0.2, 2.2, 4.2, 6.2, 8.2, 10.2, 12.2, 14.2, 20.2, 30.2],
    )

    assert [item["label"] for item in phrase_map] == [
        "intro", "verse", "verse", "chorus",
    ]
    assert phrase_map[1]["end"] == phrase_map[2]["start"] == 20.0
    assert all(item["source"] == "all_in_one_functional_segment" for item in phrase_map)


def test_intro_hot_cue_uses_model_boundary_not_energy_threshold() -> None:
    phrase_map = _all_in_one_segments_to_phrase_map(_segments())
    phrase_map[0]["energy"] = 0.95
    phrase_map[1]["energy"] = 0.1

    cues = _generate_dj_hot_cues(phrase_map, [], [], 42.0)
    intro_end = next(item for item in cues if item["name"] == "intro_end")

    assert intro_end["time"] == 10.0
    assert intro_end["source"] == "all_in_one_intro_boundary"
