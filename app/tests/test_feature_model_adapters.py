from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import soundfile as sf

from app.modules.library.drum_analysis import analyze_drum_stem
from app.modules.library.feature_model_adapters import (
    FeatureModelConfig,
    collect_mature_model_evidence,
)


def _disabled_config(
    *,
    drum_command: str | None = None,
    bass_command: str | None = None,
    style_command: str | None = None,
    instrument_command: str | None = None,
) -> FeatureModelConfig:
    return FeatureModelConfig(
        drum_command=drum_command,
        bass_command=bass_command,
        style_command=style_command,
        instrument_command=instrument_command,
        timeout_seconds=10.0,
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


def test_style_worker_labels_remain_a_separate_auxiliary_route() -> None:
    with tempfile.TemporaryDirectory() as directory:
        audio_path = os.path.join(directory, "song.wav")
        sf.write(audio_path, np.zeros(8000, dtype=np.float32), 8000)
        worker_path = os.path.join(directory, "style_worker.py")
        with open(worker_path, "w", encoding="utf-8") as handle:
            handle.write(
                "import json\n"
                "print(json.dumps({'engine':'style-test','license':'test-only','labels':["
                "{'label':'Electronic---House','score':0.81},"
                "{'label':'Funk / Soul---Disco','score':0.24}]}))\n"
            )
        command = f'{sys.executable} "{worker_path}" "{{audio}}"'
        result = collect_mature_model_evidence(
            {},
            original_path=audio_path,
            config=_disabled_config(style_command=command),
        )

    route = result["routes"]["style_tags"]
    assert route["status"] == "ready"
    assert route["result"]["labels"][0]["label"] == "Electronic---House"
    assert result["ready_routes"] == ["style_tags"]
    assert result["routes"]["drum_transcription"]["status"] == "disabled"


def test_bass_and_instrument_workers_remain_separate_optional_routes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        audio_path = os.path.join(directory, "bass.wav")
        sf.write(audio_path, np.zeros(8000, dtype=np.float32), 8000)
        bass_worker = os.path.join(directory, "bass_worker.py")
        instrument_worker = os.path.join(directory, "instrument_worker.py")
        with open(bass_worker, "w", encoding="utf-8") as handle:
            handle.write(
                "import json\n"
                "print(json.dumps({'engine':'basic-pitch-test','note_events':["
                "{'start':0.5,'end':0.7,'midi':36,'confidence':0.9}]}))\n"
            )
        with open(instrument_worker, "w", encoding="utf-8") as handle:
            handle.write(
                "import json\n"
                "print(json.dumps({'engine':'instrument-test','labels':["
                "{'label':'drummachine','score':0.8}]}))\n"
            )
        result = collect_mature_model_evidence(
            {"bass": audio_path},
            original_path=audio_path,
            config=_disabled_config(
                bass_command=f'{sys.executable} "{bass_worker}" "{{audio}}"',
                instrument_command=f'{sys.executable} "{instrument_worker}" "{{audio}}"',
            ),
        )

    assert result["routes"]["bass_transcription"]["status"] == "ready"
    assert result["routes"]["instrument_tags"]["status"] == "ready"
    assert result["routes"]["bass_transcription"]["result"]["note_events"][0]["midi"] == 36
    assert set(result["ready_routes"]) == {"bass_transcription", "instrument_tags"}


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


def test_style_model_window_has_bounded_default() -> None:
    config = FeatureModelConfig.from_env()
    assert config.style_max_duration_seconds == 90.0
