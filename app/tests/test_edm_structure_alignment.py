from app.modules.edm_structure.alignment import align_edm_probabilities


LABELS = ("intro", "buildup", "drop", "breakdown", "outro", "silence")


def frame(start, end, top, probability=0.8):
    rest = (1 - probability) / 5
    values = {label: rest for label in LABELS}
    values[top] = probability
    return {"start_sec": start, "end_sec": end, "probabilities": values}


def blocks():
    return [
        {"block_id": "s1", "start_bar_index": 0, "end_bar_index": 4, "start_time": 0.0, "end_time": 8.0},
        {"block_id": "s2", "start_bar_index": 4, "end_bar_index": 12, "start_time": 8.0, "end_time": 24.0},
    ]


def test_alignment_uses_songformer_blocks_without_replacing_boundaries():
    result = align_edm_probabilities(
        [frame(0, 8, "intro"), frame(8, 24, "drop")],
        blocks(),
        boundary_candidates=[7.8, 23.7],
    )
    assert [(item.start_bar_index, item.end_bar_index) for item in result] == [(0, 4), (4, 12)]
    assert all(item.canonical_boundary_source == "songformer_bar_snap_v1" for item in result)
    assert result[0].edmformer_boundary_candidates == [7.8]


def test_short_high_probability_frame_is_overlap_weighted():
    result = align_edm_probabilities(
        [frame(0, 7.9, "intro", 0.8), frame(7.9, 8.0, "drop", 0.99)],
        blocks()[:1],
    )[0]
    assert result.edmformer_label_candidate == "intro"
