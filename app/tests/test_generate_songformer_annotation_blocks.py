from __future__ import annotations

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from app.modules.bar_annotations.songformer_sections import (
    SongFormerRunner,
    SongFormerSectionStore,
    try_generate_songformer_sections,
)
from app.modules.bar_annotations.pilot import PilotManifest
from scripts.generate_songformer_annotation_blocks import generate_pilot_sections


def _runner(tmp_path: Path) -> tuple[SongFormerRunner, SongFormerSectionStore]:
    store = SongFormerSectionStore(tmp_path / "sections")
    runner = SongFormerRunner(
        command_template=(
            "python experiments/run_songformer_isolated.py {audio} "
            "--out-dir {output_dir} --device cuda"
        ),
        work_dir=tmp_path / "work",
        timeout_sec=1800,
        store=store,
    )
    return runner, store


def _write_success_manifest(work_dir: Path, audio: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model": "ASLP-lab/SongFormer",
        "runner_version": "songformer_isolated_v3",
        "runtime_fingerprint": {
            "runner_version": "songformer_isolated_v3",
            "songformer_checkpoint_sha256": "model-sha",
        },
        "cache_namespace": "songformer-cache-a",
        "tracks": [
            {
                "audio_path": str(audio.resolve()),
                "audio_fingerprint": "audio-sha",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 4.0,
                        "label": "intro",
                        "label_zh": "前奏",
                        "label_probabilities": {"intro": 0.9, "verse": 0.1},
                        "label_confidence": 0.9,
                        "label_margin": 0.8,
                    }
                ],
            }
        ],
    }
    (work_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_runner_uses_argument_list_and_validates_manifest(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    runner, store = _runner(tmp_path)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        _write_success_manifest(tmp_path / "work", audio)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    document = runner.run(track_id="track-1", audio_path=audio)

    assert calls[0][0] == [
        "python",
        "experiments/run_songformer_isolated.py",
        str(audio.resolve()),
        "--out-dir",
        str((tmp_path / "work").resolve()),
        "--device",
        "cuda",
    ]
    assert calls[0][1] == {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": 1800,
        "shell": False,
    }
    assert document.status == "ready"
    assert document.relabeler.enabled is False
    assert document.segments[0].label == "intro"
    assert store.load("track-1") == document


def test_runner_failure_saves_bounded_failed_sidecar(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    runner, store = _runner(tmp_path)

    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(
            2,
            command,
            output="x" * 10_000,
            stderr="model failed " + ("y" * 10_000),
        )

    monkeypatch.setattr(subprocess, "run", fail)

    document = runner.run(track_id="track-1", audio_path=audio)

    assert document.status == "failed"
    assert document.segments == []
    assert document.error is not None
    assert "model failed" in document.error
    assert len(document.error) <= 4096
    assert store.load("track-1") == document


def test_force_appends_overwrite_without_using_a_shell(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    runner, _store = _runner(tmp_path)
    captured = []

    def fake_run(command, **kwargs):
        captured.append((command, kwargs))
        _write_success_manifest(tmp_path / "work", audio)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner.run(track_id="track-1", audio_path=audio, force=True)

    assert captured[0][0][-1] == "--overwrite"
    assert captured[0][1]["shell"] is False


def test_manifest_track_mismatch_fails_closed(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    different = tmp_path / "different.wav"
    different.write_bytes(b"different")
    runner, _store = _runner(tmp_path)

    def fake_run(command, **kwargs):
        _write_success_manifest(tmp_path / "work", different)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    document = runner.run(track_id="track-1", audio_path=audio)

    assert document.status == "failed"
    assert document.error == "SongFormerRuntimeError: runner manifest did not contain the requested audio"


def test_missing_audio_fails_without_invoking_subprocess(tmp_path, monkeypatch) -> None:
    runner, _store = _runner(tmp_path)
    invoked = False

    def fake_run(command, **kwargs):
        nonlocal invoked
        invoked = True

    monkeypatch.setattr(subprocess, "run", fake_run)

    document = runner.run(track_id="track-1", audio_path=tmp_path / "missing.wav")

    assert invoked is False
    assert document.status == "failed"
    assert document.error == "SongFormerRuntimeError: audio file does not exist"


class _FakeDB:
    def __init__(self, songs):
        self.songs = {song.id: song for song in songs}

    def get(self, _model, track_id):
        return self.songs.get(track_id)


class _FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, *, track_id, audio_path, force=False):
        self.calls.append((track_id, audio_path, force))
        return SimpleNamespace(status="ready", error=None, segments=[object()])


def test_pilot_dry_run_preserves_manifest_order_without_model_calls(tmp_path) -> None:
    songs = [
        SimpleNamespace(id="track-a", source_path=str(tmp_path / "a.wav")),
        SimpleNamespace(id="track-b", source_path=str(tmp_path / "b.wav")),
    ]
    runner = _FakeRunner()

    summary = generate_pilot_sections(
        manifest=PilotManifest("dataset-v1", ("track-b", "track-a")),
        db=_FakeDB(songs),
        runner=runner,
        dry_run=True,
        song_model=object,
    )

    assert [item["track_id"] for item in summary["tracks"]] == ["track-b", "track-a"]
    assert all(item["status"] == "dry_run" for item in summary["tracks"])
    assert runner.calls == []


def test_pilot_filter_processes_only_selected_manifest_tracks(tmp_path) -> None:
    audio_a = tmp_path / "a.wav"
    audio_b = tmp_path / "b.wav"
    audio_a.write_bytes(b"a")
    audio_b.write_bytes(b"b")
    songs = [
        SimpleNamespace(id="track-a", source_path=str(audio_a)),
        SimpleNamespace(id="track-b", source_path=str(audio_b)),
    ]
    runner = _FakeRunner()

    summary = generate_pilot_sections(
        manifest=PilotManifest("dataset-v1", ("track-a", "track-b")),
        db=_FakeDB(songs),
        runner=runner,
        selected_track_ids=["track-b"],
        force=True,
        song_model=object,
    )

    assert summary["ready"] == 1
    assert runner.calls == [("track-b", str(audio_b), True)]


def test_pilot_filter_rejects_tracks_outside_manifest(tmp_path) -> None:
    runner = _FakeRunner()

    with pytest.raises(ValueError, match="not in the Pilot manifest"):
        generate_pilot_sections(
            manifest=PilotManifest("dataset-v1", ("track-a",)),
            db=_FakeDB([]),
            runner=runner,
            selected_track_ids=["private-track"],
            song_model=object,
        )


def test_generation_hook_is_disabled_by_default(tmp_path) -> None:
    settings = SimpleNamespace(songformer_enabled=False)
    runner = _FakeRunner()

    result = try_generate_songformer_sections(
        SimpleNamespace(id="track-1", source_path=str(tmp_path / "song.wav")),
        settings=settings,
        runner=runner,
    )

    assert result == {"status": "disabled"}
    assert runner.calls == []


def test_generation_hook_runs_non_fatally_when_enabled(tmp_path) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    settings = SimpleNamespace(songformer_enabled=True)
    runner = _FakeRunner()

    result = try_generate_songformer_sections(
        SimpleNamespace(id="track-1", source_path=str(audio)),
        settings=settings,
        runner=runner,
    )

    assert result == {"status": "ready", "segments": 1, "error": None}
    assert runner.calls == [("track-1", str(audio), False)]
