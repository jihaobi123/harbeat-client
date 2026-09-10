from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.modules.library.same_style_preprocess import PreprocessConfig, run_same_style_preprocess


def _audio(path: Path, seconds: float = 0.2) -> None:
    samples = np.zeros((int(44100 * seconds), 2), dtype=np.float32)
    sf.write(path, samples, 44100)


def _core(_path: str) -> dict:
    return {
        "bpm": 120.0,
        "duration": 0.2,
        "energy": 0.4,
        "key": "C major",
        "camelot_key": "8B",
        "key_confidence": 0.8,
        "key_profile": {"needs_review": False},
        "beat_points": [0.0, 0.05, 0.1, 0.15],
        "downbeats": [0.0, 0.1, 0.2],
        "beat_confidence": 0.9,
        "tempo_stability": 0.9,
        "beat_needs_review": False,
        "time_signature": {"numerator": 4, "denominator": 4, "needs_review": False},
        "section_analysis": {
            "fallback_used": False,
            "functional_segments": [{"start": 0.0, "end": 0.2, "label": "intro"}],
        },
        "energy_curve": [{"start": 0.0, "end": 0.2, "relative_energy": 0.5}],
        "transition_windows": [{"start": 0.0, "end": 0.2, "mix_in_score": 0.9, "mix_out_score": 0.4}],
    }


def _stem(_paths, **_kwargs) -> dict:
    events = {
        "kick": [{"time": 0.0, "subtype": "kick"}],
        "snare": [{"time": 0.05, "subtype": "snare"}],
        "hihat": [{"time": 0.025, "subtype": "closed_hihat"}],
        "tom": [],
        "cymbal": [{"time": 0.075, "subtype": "cymbal"}],
    }
    return {
        "drum_analysis": {"status": "ready", "events": events, "quality_flags": []},
        "feature_analysis": {
            "analysis_modules": {
                "bass": {"status": "ready", "events": [{"time": 0.0}], "quality_flags": [], "features": {}},
                "percussion": {"status": "ready", "events": [], "quality_flags": []},
            }
        },
    }


def _separate(source: Path, output: Path, _config: PreprocessConfig, names: tuple[str, ...]):
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in names:
        target = output / f"{name}.wav"
        _audio(target)
        result[name] = target
    return result


def test_publisher_writes_atomic_contract_and_reuses_identical_run(tmp_path: Path) -> None:
    pytest.importorskip("jsonschema")
    source = tmp_path / "song.wav"
    _audio(source)
    root = tmp_path / "nas"
    config = PreprocessConfig.from_values(root=root, git_sha="abcdef123456", device="cpu")
    schema = Path(__file__).parents[1] / "contracts/schemas/analysis/same-style-track-preprocess-v1.schema.json"
    kwargs = {
        "config": config,
        "schema_path": schema,
        "title": "Song",
        "artist": "Artist",
        "core_runner": _core,
        "stem_analyzer": _stem,
        "demucs_runner": lambda source, output, config: _separate(source, output, config, ("vocals", "drums", "bass", "other")),
        "mdx_runner": lambda source, output, config: _separate(source, output, config, ("kick", "snare", "hihat", "tom", "cymbal")),
    }
    first = run_same_style_preprocess(source, "track-001", **kwargs)
    second = run_same_style_preprocess(source, "track-001", **kwargs)

    assert first == second
    assert first["schema_version"] == "1.1.0"
    assert first["source"]["original_filename"] == "song.wav"
    assert first["source"]["title"] == "Song"
    assert first["assets"]["master"]["storage_key"].startswith("published/tracks/")
    assert "/staging/" not in first["assets"]["master"]["storage_key"]
    assert first["analysis"]["beat_grid"]["unit"] == "ms"
    assert first["analysis"]["drum_groups"]["bass_808"]["event_count"] == 1
    run = root / "published/tracks/track-001/runs" / first["analysis_run_id"]
    assert (run / "manifest.json").is_file()
    assert (run / "_SUCCESS.json").is_file()
    latest = json.loads((root / "published/tracks/track-001/latest.json").read_text())
    assert latest["analysis_run_id"] == first["analysis_run_id"]
    assert not list((root / "locks").glob("*.lock"))


def test_publisher_rejects_unsafe_track_id(tmp_path: Path) -> None:
    source = tmp_path / "song.wav"
    _audio(source)
    config = PreprocessConfig.from_values(root=tmp_path / "nas", git_sha="abcdef1")
    with pytest.raises(ValueError, match="track_id"):
        run_same_style_preprocess(
            source,
            "../escape",
            config=config,
            schema_path=tmp_path / "unused.json",
        )
