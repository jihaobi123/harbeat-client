from __future__ import annotations

import numpy as np

from app.modules.library.percussion_feature_analysis import analyze_percussion_features


def _burst(audio: np.ndarray, sr: int, time_sec: float, signal: np.ndarray) -> None:
    start = int(time_sec * sr)
    audio[start:start + len(signal)] += signal.astype(np.float32)


def test_percussion_module_separates_short_and_sustained_metallic_families() -> None:
    sr = 12000
    duration = 8.0
    audio = np.zeros(int(sr * duration), dtype=np.float32)
    rng = np.random.default_rng(12)
    closed_times = [0.5, 1.5, 2.5, 3.5]
    open_times = [4.5, 5.5, 6.5, 7.2]
    short_t = np.arange(int(0.08 * sr)) / sr
    long_t = np.arange(int(0.42 * sr)) / sr
    short = rng.normal(0, 0.35, len(short_t)) * np.exp(-short_t * 55)
    long = rng.normal(0, 0.30, len(long_t)) * np.exp(-long_t * 8)
    for value in closed_times:
        _burst(audio, sr, value, short)
    for value in open_times:
        _burst(audio, sr, value, long)
    analysis = {"events": {"hihat": [{"time": value} for value in closed_times + open_times]}}

    result = analyze_percussion_features(audio, sr, drum_analysis=analysis)

    assert result["features"]["short_metallic"]["score"] > 0.0
    assert result["features"]["sustained_metallic"]["score"] > 0.0
    assert "closed_hihat" in result["features"]["short_metallic"]["evidence"]["candidate_labels"]
    assert "open_hihat" in result["features"]["sustained_metallic"]["evidence"]["candidate_labels"]


def test_tonal_percussion_keeps_frequency_and_candidate_evidence() -> None:
    sr = 12000
    audio = np.zeros(sr * 6, dtype=np.float32)
    times = [0.5, 1.25, 2.0, 2.75, 3.5, 4.25, 5.0]
    local = np.arange(int(0.20 * sr)) / sr
    tone = np.sin(2 * np.pi * 720 * local) * np.exp(-local * 18) * 0.6
    for value in times:
        _burst(audio, sr, value, tone)
    analysis = {"events": {"percussion": [{"time": value} for value in times]}}

    result = analyze_percussion_features(audio, sr, drum_analysis=analysis)

    tonal = result["features"]["tonal_percussion"]
    motif = result["features"]["repeated_tonal_motif"]
    assert tonal["detected"] is True
    assert motif["score"] > 0.5
    assert "cowbell" in tonal["evidence"]["candidate_labels"]
    assert tonal["evidence"]["frequency_rule_hz"]["tonal_percussion_dominant"] == [180, 3200]


def test_missing_drums_stem_is_unknown() -> None:
    result = analyze_percussion_features(None, 22050)

    assert result["status"] == "unavailable"
    assert result["features"]["wide_clap"]["detected"] is None
