"""Spotify Mix integration surface tests."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from app.main import app
from app.modules.dj_control.transition import (
    enrich_transition_plan_with_mix_effects,
    mix_effect_presets,
)
from app.modules.library.loudness import loudness_profile
from app.modules.library.time_stretch import time_stretch_song


def _song(song_id: str, **overrides):
    base = {
        "id": song_id,
        "bpm": 120.0,
        "camelot_key": "8A",
        "energy": 0.6,
        "loudness_profile": {"integrated_lufs": -14.0},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_spotify_mix_routes_are_registered():
    paths = {route.path for route in app.routes}
    assert "/api/dj/mix_effects/presets" in paths
    assert "/api/dj/mix_effects/decide" in paths
    assert "/api/dj/mix_effects/smart_reorder" in paths
    assert "/api/library/songs/{song_id}/waveform" in paths
    assert "/api/library/songs/{song_id}/normalize" in paths


def test_preset_catalog_shape():
    catalog = mix_effect_presets()
    keys = {item["key"] for item in catalog["presets"]}
    assert {"fade", "rise", "blend", "cut", "overlap"}.issubset(keys)


def test_transition_plan_enrichment_adds_curves():
    plan = {"duration_sec": 8.0, "style": "blend"}
    enriched = enrich_transition_plan_with_mix_effects(
        plan,
        _song("a", bpm=120, camelot_key="8A", energy=0.7),
        _song("b", bpm=122, camelot_key="9A", energy=0.72),
        "auto",
    )
    assert enriched["mix_preset"] == "blend"
    assert enriched["decision"]["preset"] == "blend"
    assert enriched["volume_curves"]["deck_a"]
    assert enriched["eq_curves"]["deck_a"]["low"]


def test_library_loudness_wrapper_profile():
    audio = np.random.randn(48000).astype(np.float32) * 0.05
    profile = loudness_profile(audio, 48000)
    assert "integrated_lufs" in profile
    assert profile["target_lufs"] == -14.0


def test_library_time_stretch_wrapper_returns_ratio():
    audio = np.random.randn(12000).astype(np.float32) * 0.05
    stretched, ratio = time_stretch_song(audio, 48000, 120.0, 126.0)
    assert ratio == 1.05
    assert len(stretched) < len(audio)
