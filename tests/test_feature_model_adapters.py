from __future__ import annotations

import json
import subprocess

from app.modules.library.feature_model_adapters import _run_json_command


def test_model_adapter_accepts_status_line_before_json(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "drums.wav"
    audio.write_bytes(b"audio")
    payload = {"engine": "adtof", "events": {"kick": [{"time": 0.1}]}}

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["worker"],
            returncode=0,
            stdout="Loading PyTorch weights from: checkpoint.pth\n" + json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    route = _run_json_command(
        "worker --audio {audio}",
        str(audio),
        engine="external_drum_transcriber",
        timeout_seconds=30,
    )

    assert route["status"] == "ready"
    assert route["engine"] == "adtof"
    assert route["result"] == payload


def test_model_adapter_rejects_status_output_without_json(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "drums.wav"
    audio.write_bytes(b"audio")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["worker"], returncode=0, stdout="model ready", stderr=""
        ),
    )

    route = _run_json_command(
        "worker --audio {audio}",
        str(audio),
        engine="external_drum_transcriber",
        timeout_seconds=30,
    )

    assert route["status"] == "error"
    assert "JSONDecodeError" in route["error"]
