import importlib.util
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _load_loudness():
    from harbeat_audio_runtime import loudness_normalizer
    return loudness_normalizer


def test_apply_loudness_norm_returns_audio_and_metadata():
    mod = _load_loudness()
    audio = np.random.randn(4800).astype(np.float32) * 0.05
    normalized, meta = mod.apply_loudness_norm(audio, 48000)
    assert normalized.shape == audio.shape
    assert "gain_db" in meta
    assert meta["target_lufs"] == -14.0
