import numpy as np

from experiments.extract_mert_vector_dataset import (
    _aggregate_intervals,
    _bar_intervals,
    _chunk_starts,
    _time_grid,
)


def test_chunk_starts_cover_tail_with_full_context() -> None:
    starts = _chunk_starts(11.2, 5.0, 2.5)

    assert starts == [0.0, 2.5, 5.0, 6.2]
    assert starts[-1] + 5.0 == 11.2


def test_short_audio_uses_one_chunk() -> None:
    assert _chunk_starts(3.0, 5.0, 2.5) == [0.0]


def test_time_grid_retains_partial_tail_bin() -> None:
    starts, ends = _time_grid(1.2, 0.5)

    np.testing.assert_allclose(starts, [0.0, 0.5, 1.0])
    np.testing.assert_allclose(ends, [0.5, 1.0, 1.2])


def test_time_grid_does_not_create_bin_for_one_sample_decoder_tail() -> None:
    duration = 113.0 + 1.0 / 24_000.0

    starts, ends = _time_grid(duration, 0.5)

    assert len(starts) == 226
    assert starts[-1] == 112.5
    np.testing.assert_allclose(ends[-1], duration)


def test_bar_intervals_end_at_song_duration() -> None:
    starts, ends = _bar_intervals([1.0, 3.0, 5.0], 6.2)

    np.testing.assert_allclose(starts, [1.0, 3.0, 5.0])
    np.testing.assert_allclose(ends, [3.0, 5.0, 6.2])


def test_interval_pooling_uses_fractional_overlap() -> None:
    embeddings = np.asarray([[[0.0]], [[10.0]], [[20.0]]], dtype=np.float32)
    bin_starts = np.asarray([0.0, 0.5, 1.0], dtype=np.float32)
    bin_ends = np.asarray([0.5, 1.0, 1.5], dtype=np.float32)

    pooled = _aggregate_intervals(
        embeddings,
        bin_starts,
        bin_ends,
        np.asarray([0.25], dtype=np.float32),
        np.asarray([1.25], dtype=np.float32),
    )

    np.testing.assert_allclose(pooled[:, 0, 0], [10.0])
