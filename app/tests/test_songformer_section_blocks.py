from __future__ import annotations

from types import SimpleNamespace

from app.modules.bar_annotations.section_blocks import build_section_blocks
from app.modules.bar_annotations.songformer_sections import songformer_document
from app.modules.library.bar_feature_adapter import build_canonical_timeline


def _timeline(duration: float = 8.0):
    song = SimpleNamespace(
        duration=duration,
        beat_points=[index * 0.5 for index in range(int(duration / 0.5))],
        downbeats=[index * 2.0 for index in range(int(duration / 2.0))],
        time_signature={"numerator": 4, "denominator": 4, "confidence": 0.95},
    )
    return build_canonical_timeline(song)


def _document(
    segments: list[tuple[float, float, str]],
    *,
    cache_namespace: str = "songformer-cache-a",
):
    return songformer_document(
        track_id="track-1",
        audio_fingerprint="audio-sha",
        runtime_fingerprint={"runner_version": "songformer_isolated_v3"},
        cache_namespace=cache_namespace,
        segments=[
            {"start": start, "end": end, "label": label}
            for start, end, label in segments
        ],
    )


def test_snaps_boundaries_to_nearest_bar_edges() -> None:
    blocks = build_section_blocks(
        track_id="track-1",
        timeline=_timeline(),
        document=_document([(0.12, 3.82, "intro"), (3.82, 8.0, "verse")]),
    )

    assert [(item.start_bar_index, item.end_bar_index) for item in blocks] == [
        (0, 2),
        (2, 4),
    ]
    assert blocks[0].raw_start_time == 0.12
    assert blocks[0].raw_end_time == 3.82
    assert blocks[0].start_time == 0.0
    assert blocks[0].end_time == 4.0
    assert blocks[0].end_snap_error_sec == 0.18


def test_large_snap_error_marks_adjacent_blocks_for_review() -> None:
    blocks = build_section_blocks(
        track_id="track-1",
        timeline=_timeline(),
        document=_document([(0.0, 3.0, "intro"), (3.0, 8.0, "verse")]),
    )

    assert len(blocks) == 2
    assert blocks[0].needs_review is True
    assert blocks[1].needs_review is True
    assert blocks[0].end_snap_error_sec == 1.0
    assert blocks[1].start_snap_error_sec == 1.0


def test_collapsed_boundaries_never_create_zero_length_blocks() -> None:
    blocks = build_section_blocks(
        track_id="track-1",
        timeline=_timeline(duration=4.0),
        document=_document(
            [(0.0, 1.1, "intro"), (1.1, 1.2, "verse"), (1.2, 4.0, "chorus")]
        ),
    )

    assert [(item.start_bar_index, item.end_bar_index) for item in blocks] == [
        (0, 1),
        (1, 2),
    ]
    assert all(item.start_bar_index < item.end_bar_index for item in blocks)
    assert any(item.suppressed_boundary_count > 0 for item in blocks)


def test_song_edges_cover_the_complete_bar_timeline() -> None:
    blocks = build_section_blocks(
        track_id="track-1",
        timeline=_timeline(),
        document=_document([(0.4, 4.2, "intro"), (4.2, 7.6, "verse")]),
    )

    assert blocks[0].start_bar_index == 0
    assert blocks[-1].end_bar_index == 4
    assert blocks[0].start_time == 0.0
    assert blocks[-1].end_time == 8.0


def test_block_ids_are_stable_and_change_with_runtime_namespace() -> None:
    first = build_section_blocks(
        track_id="track-1",
        timeline=_timeline(),
        document=_document([(0.0, 4.0, "intro"), (4.0, 8.0, "verse")]),
    )
    repeated = build_section_blocks(
        track_id="track-1",
        timeline=_timeline(),
        document=_document([(0.0, 4.0, "intro"), (4.0, 8.0, "verse")]),
    )
    changed = build_section_blocks(
        track_id="track-1",
        timeline=_timeline(),
        document=_document(
            [(0.0, 4.0, "intro"), (4.0, 8.0, "verse")],
            cache_namespace="songformer-cache-b",
        ),
    )

    assert [item.block_id for item in first] == [item.block_id for item in repeated]
    assert [item.block_id for item in first] != [item.block_id for item in changed]


def test_blocks_preserve_source_segment_indexes_and_model_fingerprint() -> None:
    blocks = build_section_blocks(
        track_id="track-1",
        timeline=_timeline(),
        document=_document([(0.0, 4.0, "intro"), (4.0, 8.0, "verse")]),
    )

    assert blocks[0].source == "songformer_bar_snap_v1"
    assert blocks[0].source_segment_indexes == [0]
    assert len(blocks[0].model_runtime_fingerprint) == 64
