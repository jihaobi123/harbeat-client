import json
from pathlib import Path

import pytest

from app.modules.edm_structure.runner import (
    EdmStructureRunner,
    EdmRuntimeError,
)


def valid_manifest(audio_path: Path) -> dict:
    probabilities = {
        "intro": 0.7,
        "buildup": 0.1,
        "drop": 0.05,
        "breakdown": 0.05,
        "outro": 0.05,
        "silence": 0.05,
    }
    return {
        "schema_name": "harbeat.edmformer_runtime_manifest",
        "schema_version": "0.1.0",
        "runtime_fingerprint": {
            "runner_version": "edmformer_isolated_v1",
            "source_revision": "2dd942f2f9e71ffd826346828eeaba1dd3ece56a",
        },
        "tracks": [
            {
                "audio_path": str(audio_path.resolve()),
                "audio_sha256": "a" * 64,
                "duration_sec": 2.0,
                "status": "ready",
                "frames": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 0.12,
                        "probabilities": probabilities,
                    }
                ],
                "boundary_candidates": [1.25],
                "muq_sha256": "b" * 64,
                "musicfm_sha256": "c" * 64,
                "musicfm_stats_sha256": "d" * 64,
                "edmformer_sha256": "e" * 64,
                "warnings": [],
                "error": None,
            }
        ],
    }


def test_command_requires_bounded_placeholders(tmp_path):
    runner = EdmStructureRunner(
        command_template="python runtime.py --audio {audio} --output-dir {output_dir}",
        work_dir=tmp_path / "work",
        timeout_sec=30,
    )
    audio = tmp_path / "song with spaces.wav"
    audio.write_bytes(b"RIFF")
    command = runner._command(audio.resolve())
    assert command[-3:] == [str(audio.resolve()), "--output-dir", str((tmp_path / "work").resolve())]

    broken = EdmStructureRunner(
        command_template="python runtime.py --audio {audio}",
        work_dir=tmp_path / "other",
        timeout_sec=30,
    )
    with pytest.raises(EdmRuntimeError, match="output_dir"):
        broken._command(audio.resolve())


def test_runner_reads_only_the_requested_track(tmp_path, monkeypatch):
    work_dir = tmp_path / "work"
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"RIFF")
    manifest = valid_manifest(audio)
    work_dir.mkdir()
    (work_dir / "manifest.json").write_text(json.dumps(manifest))
    runner = EdmStructureRunner(
        command_template="python runtime.py --audio {audio} --output-dir {output_dir}",
        work_dir=work_dir,
        timeout_sec=30,
    )
    monkeypatch.setattr(runner, "_execute", lambda _command: None)
    result = runner.run(track_id="track-1", audio_path=audio)
    assert result.track_id == "track-1"
    assert result.frames[0].probabilities["intro"] == 0.7
    assert result.runtime_fingerprint["runner_version"] == "edmformer_isolated_v1"


def test_runner_rejects_nonfinite_or_unrelated_output(tmp_path, monkeypatch):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"RIFF")
    manifest = valid_manifest(audio)
    manifest["tracks"][0]["frames"][0]["probabilities"]["intro"] = float("nan")
    (work_dir / "manifest.json").write_text(json.dumps(manifest))
    runner = EdmStructureRunner(
        command_template="python runtime.py --audio {audio} --output-dir {output_dir}",
        work_dir=work_dir,
        timeout_sec=30,
    )
    monkeypatch.setattr(runner, "_execute", lambda _command: None)
    with pytest.raises(EdmRuntimeError, match="non-finite"):
        runner.run(track_id="track-1", audio_path=audio)

    manifest = valid_manifest(tmp_path / "different.wav")
    (work_dir / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(EdmRuntimeError, match="requested audio"):
        runner.run(track_id="track-1", audio_path=audio)
