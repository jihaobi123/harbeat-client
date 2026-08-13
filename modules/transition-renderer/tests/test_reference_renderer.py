import json
from types import SimpleNamespace

import numpy as np
import soundfile as sf

from harbeat_transition_renderer import (
    FAST_CUT_RENDERER_VERSION,
    RENDERER_VERSION,
    ensure_reference_render,
)
from harbeat_transition_renderer import reference_renderer


def _song(song_id, path, *, bpm=100.0):
    duration = 20.0
    beat = 60.0 / bpm
    beats = [round(i * beat, 3) for i in range(int(duration / beat))]
    return SimpleNamespace(
        id=song_id,
        source_path=str(path),
        bpm=bpm,
        beat_points=beats,
        downbeats=beats[::4],
    )


def _wav_pair(tmp_path):
    sr = 44100
    duration = 20.0
    t = np.arange(int(sr * duration), dtype=np.float32) / sr
    prev_path = tmp_path / "prev.wav"
    next_path = tmp_path / "next.wav"
    sf.write(prev_path, 0.18 * np.sin(2 * np.pi * 110 * t), sr)
    sf.write(next_path, 0.18 * np.sin(2 * np.pi * 165 * t), sr)
    return _song("prev", prev_path), _song("next", next_path)


def _plan(pair_id, renderer_version, *, playback_mode="fast_cut"):
    return {
        "pair_id": pair_id,
        "playback_mode": playback_mode,
        "default_mix": {
            "pair_id": pair_id,
            "required_renderer_version": renderer_version,
            "renderer_version": renderer_version,
            "planner_version": "test-planner",
            "audio_feature_source": "dj_structure_precomputed_window_v2",
            "from_at_sec": 3.0,
            "to_at_sec": 4.0,
            "duration_sec": 3.0,
        },
    }


def test_fast_cut_renders_local_windows_and_writes_metadata(tmp_path, monkeypatch):
    prev, nxt = _wav_pair(tmp_path)
    monkeypatch.setattr(reference_renderer, "pair_cache_root", lambda: tmp_path / "pairs")

    meta = ensure_reference_render(
        prev,
        nxt,
        _plan("fast-local-window", FAST_CUT_RENDERER_VERSION),
    )

    assert meta["renderer_version"] == FAST_CUT_RENDERER_VERSION
    assert meta["audio_window_loading"]["mode"] == "random_access_local_window_v7"
    assert meta["audio_window_loading"]["track1"]["duration_sec"] < 20.0
    assert meta["audio_window_loading"]["track2"]["duration_sec"] < 20.0
    assert meta["render_timing_ms"]["total"] >= 0.0
    assert (tmp_path / "pairs" / "fast-local-window" / "transition_render.wav").is_file()
    meta_path = tmp_path / "pairs" / "fast-local-window" / "transition_render.json"
    assert json.loads(meta_path.read_text(encoding="utf-8"))["pair_id"] == "fast-local-window"


def test_cached_render_is_reused(tmp_path, monkeypatch):
    prev, nxt = _wav_pair(tmp_path)
    monkeypatch.setattr(reference_renderer, "pair_cache_root", lambda: tmp_path / "pairs")
    plan = _plan("cached-pair", FAST_CUT_RENDERER_VERSION)

    first = ensure_reference_render(prev, nxt, plan)
    second = ensure_reference_render(prev, nxt, plan)

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["transition_render_path"] == first["transition_render_path"]


def test_normal_renderer_uses_v9_local_window_path(tmp_path, monkeypatch):
    prev, nxt = _wav_pair(tmp_path)
    monkeypatch.setattr(reference_renderer, "pair_cache_root", lambda: tmp_path / "pairs")

    meta = ensure_reference_render(
        prev,
        nxt,
        _plan("normal-render", RENDERER_VERSION, playback_mode="default_mix"),
    )

    assert meta["renderer_version"] == RENDERER_VERSION
    assert meta["audio_window_loading"]["mode"] == "random_access_local_window_v1"
    assert meta["render_timing_ms"]["total"] >= 0.0
