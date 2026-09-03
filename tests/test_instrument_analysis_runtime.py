import pytest

from experiments.run_instrument_analysis_isolated import (
    broad_instrument_scores,
    iter_audio_windows,
    panns_compute_precision,
)


def test_audio_windows_cover_short_and_long_tracks():
    assert list(iter_audio_windows(4.0, window_sec=10.0, hop_sec=5.0)) == [(0.0, 4.0)]
    assert list(iter_audio_windows(14.0, window_sec=10.0, hop_sec=5.0)) == [
        (0.0, 10.0),
        (5.0, 14.0),
        (10.0, 14.0),
    ]


def test_broad_instrument_scores_use_max_of_exact_audioset_labels():
    labels = ["Bass guitar", "Double bass", "Speech", "Music"]
    scores = [0.4, 0.8, 0.6, 0.9]
    mapped = broad_instrument_scores(labels, scores)
    assert mapped["bass"] == pytest.approx(0.8)
    assert mapped["voice"] == pytest.approx(0.6)
    assert "piano" not in mapped


def test_broad_instrument_scores_reject_length_mismatch():
    with pytest.raises(ValueError, match="length"):
        broad_instrument_scores(["Bass guitar"], [0.1, 0.2])


def test_panns_keeps_float32_when_runtime_requests_cuda_float16():
    """PANNs produces non-finite clip probabilities under Jetson FP16 autocast."""
    assert panns_compute_precision("float16", "cuda") == "float32"
    assert panns_compute_precision("float32", "cuda") == "float32"
