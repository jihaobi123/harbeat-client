import importlib.util
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _load_loudness():
    spec = importlib.util.spec_from_file_location(
        "loudness_normalizer_for_test",
        ROOT / "audio-engine" / "loudness_normalizer.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_apply_loudness_norm_returns_audio_and_metadata():
    mod = _load_loudness()
    audio = np.random.randn(4800).astype(np.float32) * 0.05
    normalized, meta = mod.apply_loudness_norm(audio, 48000)
    assert normalized.shape == audio.shape
    assert "gain_db" in meta
    assert meta["target_lufs"] == -14.0
