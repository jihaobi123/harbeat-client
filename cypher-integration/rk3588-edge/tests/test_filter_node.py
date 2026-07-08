import importlib.util
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _load_filter_node():
    spec = importlib.util.spec_from_file_location(
        "filter_node_for_test",
        ROOT / "audio-engine" / "filter_node.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_lowpass_preserves_shape():
    mod = _load_filter_node()
    audio = np.random.randn(2048, 2).astype(np.float32) * 0.1
    out = mod.FilterNode().apply_lowpass(audio, 48000, 1000.0)
    assert out.shape == audio.shape


def test_dynamic_filter_accepts_spotify_curve():
    mod = _load_filter_node()
    audio = np.random.randn(4096).astype(np.float32) * 0.1
    out = mod.apply_filter_plan(audio, 48000, {
        "filter_type": "highpass",
        "frequency": [(0.0, 20.0), (0.04, 2000.0)],
    })
    assert out.shape == audio.shape
