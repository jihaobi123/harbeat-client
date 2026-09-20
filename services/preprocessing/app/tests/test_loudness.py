"""LUFS loudness unit tests."""
import numpy as np
import pytest

from app.modules.dj_control.spotify_mix.loudness import (
    SPOTIFY_TARGET_LUFS,
    calculate_replay_gain,
    detect_clipping,
    measure_lufs,
    normalize_to_lufs,
    peak_dbfs,
)


class TestMeasureLUFS:
    def test_silence_is_low(self):
        silence = np.zeros(48000)
        lufs = measure_lufs(silence, 48000)
        assert lufs < -50

    def test_louder_signal_higher_lufs(self):
        sr = 48000
        quiet = np.random.randn(sr) * 0.05
        loud = np.random.randn(sr) * 0.5
        lufs_quiet = measure_lufs(quiet, sr)
        lufs_loud = measure_lufs(loud, sr)
        assert lufs_loud > lufs_quiet


class TestNormalize:
    def test_silence_unchanged(self):
        audio = np.zeros(1000)
        normalized, _, _ = normalize_to_lufs(audio, 48000)
        assert len(normalized) == 1000

    def test_returns_three_values(self):
        audio = np.random.randn(48000) * 0.3
        result = normalize_to_lufs(audio, 48000)
        assert len(result) == 3

    def test_normalized_clamped(self):
        audio = np.random.randn(48000) * 0.5
        normalized, _, _ = normalize_to_lufs(audio, 48000)
        assert normalized.max() <= 1.0
        assert normalized.min() >= -1.0


class TestReplayGain:
    def test_returns_dB(self):
        audio = np.random.randn(48000) * 0.3
        gain = calculate_replay_gain(audio, 48000)
        assert isinstance(gain, float)


class TestClipping:
    def test_no_clipping(self):
        audio = np.linspace(-0.5, 0.5, 1000)
        assert not detect_clipping(audio)

    def test_detects_clipping(self):
        audio = np.ones(1000) * 1.0
        assert detect_clipping(audio)

    def test_empty_audio(self):
        assert not detect_clipping(np.array([]))


class TestPeakDBFS:
    def test_silence(self):
        assert peak_dbfs(np.zeros(100)) < -60

    def test_full_scale_is_zero(self):
        audio = np.array([1.0, -1.0, 0.5])
        assert peak_dbfs(audio) == pytest.approx(0.0, abs=0.1)

    def test_half_scale(self):
        audio = np.array([0.5, -0.5])
        assert peak_dbfs(audio) == pytest.approx(-6.0, abs=0.5)
