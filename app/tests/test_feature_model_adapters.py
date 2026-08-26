from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import soundfile as sf

from app.modules.library.drum_analysis import analyze_drum_stem
from app.modules.library.feature_model_adapters import (
    FeatureModelConfig,
    _pitch_slide_ranges,
    collect_mature_model_evidence,
)
from app.modules.library.style_feature_analysis import _apply_mature_model_evidence, _feature


def _disabled_config(*, drum_command: str | None = None, tagger_command: str | None = None) -> FeatureModelConfig:
    return FeatureModelConfig(
        drum_command=drum_command,
        tagger_command=tagger_command,
        basic_pitch_command=None,
        enable_torchcrepe=False,
        enable_basic_pitch=False,
        timeout_seconds=10.0,
        torchcrepe_model="tiny",
        torchcrepe_device="cpu",
    )


def test_json_worker_contract_is_collected_without_shell_execution() -> None:
    with tempfile.TemporaryDirectory() as directory:
        audio_path = os.path.join(directory, "drums.wav")
        sf.write(audio_path, np.zeros(8000, dtype=np.float32), 8000)
        worker_path = os.path.join(directory, "worker.py")
        with open(worker_path, "w", encoding="utf-8") as handle:
            handle.write(
                "import json, sys\n"
                "print(json.dumps({'engine':'adtof-test','license':'test-only','events':"
                "{'kick':[{'time':0.5,'confidence':0.9}],'tom':[1.0]}}))\n"
            )
        command = f'{sys.executable} "{worker_path}" "{{audio}}"'
        result = collect_mature_model_evidence(
            {"drums": audio_path},
            config=_disabled_config(drum_command=command),
        )

    route = result["routes"]["drum_transcription"]
    assert route["status"] == "ready"
    assert route["engine"] == "adtof-test"
    assert route["result"]["events"]["tom"] == [1.0]
    assert result["ready_routes"] == ["drum_transcription"]


def test_dedicated_drum_model_replaces_spectral_fallback() -> None:
    sr = 8000
    audio = np.zeros(sr * 3, dtype=np.float32)
    model_route = {
        "engine": "mature-test",
        "status": "ready",
        "result": {
            "engine": "mature-test",
            "events": {
                "kick": [{"time": 0.0, "confidence": 0.9}],
                "snare": [{"time": 0.5, "confidence": 0.8}],
                "hihat": [{"time": 0.25, "confidence": 0.7}],
                "tom": [{"time": 1.0, "confidence": 0.85}],
                "cymbal": [{"time": 2.0, "confidence": 0.88}],
            },
        },
    }
    # The stem must be non-silent because separation quality is validated before
    # either transcription route is selected.
    audio[::400] = 0.4
    result = analyze_drum_stem(
        audio,
        sr,
        bpm=120.0,
        beat_points=[value / 2 for value in range(6)],
        downbeats=[0.0, 2.0],
        model_route=model_route,
    )

    assert result["selected_engine"] == "mature-test"
    assert result["detector_mode"] == "dedicated_model"
    assert result["counts"]["tom"] == 1
    assert result["counts"]["cymbal"] == 1
    assert "spectral_proxy_fallback" not in result["quality_flags"]


def test_pitch_slide_detection_uses_model_pitch_and_confidence() -> None:
    frames = 100
    midi = np.linspace(36.0, 43.0, frames)
    pitch = 440.0 * np.power(2.0, (midi - 69.0) / 12.0)
    confidence = np.full(frames, 0.92)

    ranges = _pitch_slide_ranges(pitch, confidence, hop_seconds=0.01)

    assert ranges
    assert max(abs(item["motion_semitones"]) for item in ranges) >= 5.0
    assert min(item["confidence"] for item in ranges) >= 0.9


def test_pre_style_features_prefer_detailed_model_events_and_semantics() -> None:
    low = {"sliding_808": _feature(0.0)}
    percussion = {
        name: _feature(0.0)
        for name in ("clap", "rim_snap", "closed_hihat", "open_hihat", "ride_crash", "tom")
    }
    sonic = {"brightness": _feature(0.0), "acousticness": _feature(0.0)}
    evidence = {
        "routes": {
            "drum_transcription": {
                "status": "ready",
                "engine": "drum-model-test",
                "result": {
                    "events": {
                        "clap": [{"time": 1.0, "confidence": 0.91}],
                        "open_hihat": [{"time": 1.5, "confidence": 0.88}],
                        "tom": [{"time": 2.0, "confidence": 0.86}],
                    }
                },
            },
            "bass_pitch": {"status": "unavailable", "result": {}},
            "bass_notes": {"status": "unavailable", "result": {}},
            "audio_tags": {
                "status": "ready",
                "engine": "audio-model-test",
                "result": {"features": {"brightness": 0.82, "acousticness": 0.2}},
            },
        }
    }

    selected = _apply_mature_model_evidence(
        {"hihat_roll": _feature(0.0)}, low, percussion, sonic,
        model_evidence=evidence, duration=30.0,
    )

    assert percussion["clap"]["detected"] is True
    assert percussion["open_hihat"]["detected"] is True
    assert percussion["tom"]["detected"] is True
    assert percussion["clap"]["evidence"]["source_type"] == "mature_model"
    assert sonic["brightness"]["score"] == 0.82
    assert set(selected) == {"drum-model-test", "audio-model-test"}
