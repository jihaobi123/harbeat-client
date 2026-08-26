from __future__ import annotations

import numpy as np

from app.modules.library.drum_analysis import analyze_drum_stem, empty_drum_analysis


def _add_tone(audio: np.ndarray, sr: int, at: float, frequency: float, duration: float, amplitude: float) -> None:
    start = int(round(at * sr))
    count = min(int(round(duration * sr)), len(audio) - start)
    if count <= 0:
        return
    time = np.arange(count) / sr
    envelope = np.exp(-time * 35.0)
    audio[start:start + count] += amplitude * np.sin(2 * np.pi * frequency * time) * envelope


def _synthetic_drum_loop() -> tuple[np.ndarray, int, list[float], list[float]]:
    sr = 22050
    duration = 8.0
    audio = np.zeros(int(sr * duration), dtype=np.float32)
    for at in np.arange(0.0, duration, 1.0):
        _add_tone(audio, sr, float(at), 65.0, 0.16, 0.95)
    for at in np.arange(0.5, duration, 1.0):
        _add_tone(audio, sr, float(at), 1600.0, 0.10, 0.72)
    for at in np.arange(0.0, duration, 0.25):
        _add_tone(audio, sr, float(at), 7600.0, 0.035, 0.34)
    beats = [float(value) for value in np.arange(0.0, duration, 0.5)]
    downbeats = [float(value) for value in np.arange(0.0, duration, 2.0)]
    return np.clip(audio, -1.0, 1.0), sr, beats, downbeats


def test_drum_analyzer_detects_three_classes_and_pattern() -> None:
    audio, sr, beats, downbeats = _synthetic_drum_loop()
    result = analyze_drum_stem(
        audio,
        sr,
        bpm=120.0,
        beat_points=beats,
        downbeats=downbeats,
        separation_quality=0.95,
    )

    assert result["status"] == "ready"
    assert result["counts"]["kick"] >= 6
    assert result["counts"]["snare"] >= 6
    assert result["counts"]["hihat"] >= 20
    assert result["counts"]["kick"] <= 9
    assert result["counts"]["snare"] <= 12
    assert result["pattern"]["bars_analyzed"] == 3
    assert result["pattern"]["dominant"]["kick"].count("K") >= 2
    assert result["pattern"]["dominant"]["snare"].count("S") >= 2
    assert result["pattern"]["stability"] >= 2 / 3
    assert result["confidence"]["overall"] >= 0.58
    assert result["density_curve"]


def test_drum_analyzer_degrades_without_beat_grid() -> None:
    audio, sr, _beats, _downbeats = _synthetic_drum_loop()
    result = analyze_drum_stem(audio, sr, separation_quality=0.9)

    assert result["status"] == "ready"
    assert result["needs_review"] is True
    assert "beat_grid_unavailable" in result["quality_flags"]
    assert result["pattern"]["bars_analyzed"] == 0


def test_empty_drum_analysis_is_explicitly_unavailable() -> None:
    result = empty_drum_analysis("missing_test_stem")

    assert result["status"] == "unavailable"
    assert result["needs_review"] is True
    assert result["counts"] == {"kick": 0, "snare": 0, "hihat": 0}
