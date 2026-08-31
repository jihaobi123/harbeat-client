from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.modules.library.bar_timeline import BarWindow
from app.modules.library.presence_analysis import (
    PresenceAnalysisError,
    analyze_bar_presence,
)


def _bars(count: int, seconds_per_bar: float = 2.0) -> tuple[BarWindow, ...]:
    return tuple(
        BarWindow(
            index=index,
            start_sec=index * seconds_per_bar,
            end_sec=(index + 1) * seconds_per_bar,
            beat_start_index=index * 4,
            beat_count=4,
            is_partial=False,
        )
        for index in range(count)
    )


def _write(path: Path, audio: np.ndarray, sample_rate: int) -> str:
    sf.write(path, audio.astype(np.float32), sample_rate)
    return str(path)


def _write_stems(
    tmp_path: Path,
    *,
    vocals: np.ndarray,
    drums: np.ndarray,
    bass: np.ndarray,
    other: np.ndarray,
    sample_rate: int,
) -> dict[str, str]:
    return {
        name: _write(tmp_path / f"{name}.wav", audio, sample_rate)
        for name, audio in {
            "vocals": vocals,
            "drums": drums,
            "bass": bass,
            "other": other,
        }.items()
    }


def test_detects_vocal_presence_on_bar_boundaries(tmp_path: Path):
    sample_rate = 1000
    duration = 8
    silence = np.zeros(sample_rate * duration, dtype=np.float32)
    vocals = silence.copy()
    active_time = np.arange(sample_rate * 4) / sample_rate
    vocals[sample_rate * 2:sample_rate * 6] = (
        0.4 * np.sin(2 * np.pi * 220 * active_time)
    )
    paths = _write_stems(
        tmp_path,
        vocals=vocals,
        drums=silence,
        bass=silence,
        other=silence,
        sample_rate=sample_rate,
    )

    result = analyze_bar_presence(paths, _bars(4))

    vocal = result["elements"]["vocal"]
    assert vocal["availability"] == "available"
    assert [
        (item["start_bar_index"], item["end_bar_index"])
        for item in vocal["candidate_ranges"]
    ] == [(1, 3)]
    assert vocal["bar_probabilities"][0] < 0.1
    assert vocal["bar_probabilities"][1] > 0.8


def test_marks_missing_stem_unavailable(tmp_path: Path):
    vocals_path = _write(
        tmp_path / "vocals.wav",
        np.zeros(2000, dtype=np.float32),
        1000,
    )

    result = analyze_bar_presence({"vocals": vocals_path}, _bars(1))

    assert result["elements"]["vocal"]["availability"] == "available"
    assert result["elements"]["bass"]["availability"] == "unavailable"
    assert result["elements"]["bass"]["candidate_ranges"] == []


def test_preserves_single_bar_drum_event(tmp_path: Path):
    sample_rate = 1000
    silence = np.zeros(sample_rate * 8, dtype=np.float32)
    drums = silence.copy()
    one_bar_time = np.arange(sample_rate * 2) / sample_rate
    drums[sample_rate * 4:sample_rate * 6] = (
        0.45 * np.sign(np.sin(2 * np.pi * 5 * one_bar_time))
    )
    paths = _write_stems(
        tmp_path,
        vocals=silence,
        drums=drums,
        bass=silence,
        other=silence,
        sample_rate=sample_rate,
    )

    result = analyze_bar_presence(paths, _bars(4))

    assert [
        (item["start_bar_index"], item["end_bar_index"])
        for item in result["elements"]["drums"]["candidate_ranges"]
    ] == [(2, 3)]


def test_rejects_mismatched_sample_rates(tmp_path: Path):
    vocals = _write(
        tmp_path / "vocals.wav",
        np.zeros(4000, dtype=np.float32),
        1000,
    )
    drums = _write(
        tmp_path / "drums.wav",
        np.zeros(8000, dtype=np.float32),
        2000,
    )

    with pytest.raises(PresenceAnalysisError, match="sample rate"):
        analyze_bar_presence({"vocals": vocals, "drums": drums}, _bars(2))


def test_melody_candidates_are_always_marked_for_review(tmp_path: Path):
    sample_rate = 2000
    duration = 4
    time = np.arange(sample_rate * duration) / sample_rate
    other = (0.35 * np.sin(2 * np.pi * 330 * time)).astype(np.float32)
    silence = np.zeros_like(other)
    paths = _write_stems(
        tmp_path,
        vocals=silence,
        drums=silence,
        bass=silence,
        other=other,
        sample_rate=sample_rate,
    )

    result = analyze_bar_presence(paths, _bars(2))

    melody = result["elements"]["melody"]
    assert melody["requires_review"] is True
    assert melody["confidence_cap"] == 0.65
    assert all(value <= 0.65 for value in melody["bar_probabilities"])
