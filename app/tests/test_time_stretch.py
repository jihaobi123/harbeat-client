"""Time stretching unit tests."""
import numpy as np
import pytest

from app.modules.dj_control.spotify_mix.time_stretch import (
    compute_tempo_ratio,
    phase_vocoder_stretch,
    time_stretch_to_bpm,
)


class TestComputeTempoRatio:
    def test_same_bpm_returns_one(self):
        assert compute_tempo_ratio(120, 120) == 1.0

    def test_double_bpm_returns_two(self):
        assert compute_tempo_ratio(120, 240) == 2.0

    def test_half_bpm_returns_half(self):
        assert compute_tempo_ratio(120, 60) == pytest.approx(0.5)

    def test_zero_source_bpm_returns_one(self):
        assert compute_tempo_ratio(0, 120) == 1.0


class TestPhaseVocoderStretch:
    def test_ratio_one_unchanged(self):
        audio = np.random.randn(1000)
        stretched = phase_vocoder_stretch(audio, 44100, 1.0)
        np.testing.assert_array_almost_equal(audio, stretched)

    def test_faster_is_shorter(self):
        audio = np.random.randn(10000)
        stretched = phase_vocoder_stretch(audio, 44100, 1.5)
        assert len(stretched) < len(audio)

    def test_slower_is_longer(self):
        audio = np.random.randn(10000)
        stretched = phase_vocoder_stretch(audio, 44100, 0.8)
        assert len(stretched) > len(audio)

    def test_zero_ratio_unchanged(self):
        audio = np.random.randn(1000)
        stretched = phase_vocoder_stretch(audio, 44100, 0.0)
        np.testing.assert_array_equal(audio, stretched)


class TestTimeStretchToBPM:
    def test_returns_ratio(self):
        audio = np.random.randn(10000)
        stretched, ratio = time_stretch_to_bpm(audio, 44100, 120, 130)
        assert ratio == pytest.approx(130 / 120, rel=0.01)

    def test_length_changes(self):
        audio = np.random.randn(10000)
        stretched, _ = time_stretch_to_bpm(audio, 44100, 120, 130)
        # Faster tempo → shorter audio
        assert len(stretched) < len(audio)
