import json
from pathlib import Path

import pytest

from app.modules.instrument_analysis.runner import (
    InstrumentAnalysisRunner,
    InstrumentRuntimeError,
)


def runner(tmp_path: Path, command: str = "python runtime.py --audio {audio} --output-dir {output_dir}"):
    return InstrumentAnalysisRunner(
        command_template=command,
        work_dir=tmp_path,
        timeout_sec=30,
    )


def write_runtime_manifest(tmp_path: Path, *, audio_path: str) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_name": "harbeat.instrument_runtime_manifest",
                "schema_version": "0.1.0",
                "runtime_fingerprint": {"runner_version": "test"},
                "tracks": [
                    {
                        "audio_path": audio_path,
                        "audio_sha256": "a" * 64,
                        "duration_sec": 10.0,
                        "status": "partial",
                        "models": {
                            "adtof": {
                                "availability": "unavailable",
                                "checkpoint_sha256": None,
                                "source_revision": None,
                                "events": [],
                                "elapsed_seconds": 0.0,
                                "peak_cuda_bytes": 0,
                                "error": "DRUMS_STEM_MISSING",
                            },
                            "panns": {
                                "availability": "available",
                                "checkpoint_sha256": "b" * 64,
                                "source_revision": "c" * 40,
                                "windows": [
                                    {
                                        "start_sec": 0.0,
                                        "end_sec": 10.0,
                                        "scores": [0.1, 0.9],
                                    }
                                ],
                                "labels": ["Speech", "Music"],
                                "elapsed_seconds": 1.0,
                                "peak_cuda_bytes": 123,
                                "error": None,
                            },
                        },
                        "warnings": ["DRUMS_STEM_MISSING"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_runner_requires_drums_stem_for_adtof(tmp_path, monkeypatch):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    write_runtime_manifest(tmp_path, audio_path=str(audio.resolve()))
    instance = runner(tmp_path)
    monkeypatch.setattr(instance, "_execute", lambda *_args, **_kwargs: None)

    result = instance.run(track_id="t1", audio_path=audio, stems={})

    assert result.models["adtof"].availability == "unavailable"
    assert "DRUMS_STEM_MISSING" in result.warnings


def test_runner_rejects_manifest_for_another_audio(tmp_path):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    write_runtime_manifest(tmp_path, audio_path="/other/song.wav")
    with pytest.raises(InstrumentRuntimeError, match="requested audio"):
        runner(tmp_path)._read_result(audio)


def test_command_uses_argument_list_and_optional_drums_stem(tmp_path):
    instance = runner(
        tmp_path,
        command="python runtime.py --audio {audio} --output-dir {output_dir} --drums-stem {drums_stem}",
    )
    audio = tmp_path / "song one.wav"
    drums = tmp_path / "drums one.wav"
    command = instance._command(audio, drums)
    assert command[:2] == ["python", "runtime.py"]
    assert str(audio) in command
    assert str(drums) in command
    assert "shell=True" not in command


def test_manifest_rejects_non_finite_scores(tmp_path):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    write_runtime_manifest(tmp_path, audio_path=str(audio.resolve()))
    payload = json.loads((tmp_path / "manifest.json").read_text())
    payload["tracks"][0]["models"]["panns"]["windows"][0]["scores"][0] = float("nan")
    (tmp_path / "manifest.json").write_text(json.dumps(payload))
    with pytest.raises(InstrumentRuntimeError, match="non-finite"):
        runner(tmp_path)._read_result(audio)
