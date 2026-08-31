import json
from pathlib import Path

from app.modules.library.analysis import (
    _select_authoritative_sections,
    _songformer_command,
    _songformer_payload_from_output,
)


def _segments(label: str, split: float) -> list[dict]:
    return [
        {"start": 0.0, "end": split, "label": "intro"},
        {"start": split, "end": 30.0, "label": label},
    ]


def test_songformer_sections_are_authoritative_without_blending() -> None:
    songformer = {
        "engine": "songformer:ASLP-lab/SongFormer",
        "segments": _segments("verse", 10.0),
    }
    all_in_one = {
        "engine": "all_in_one:harmonix-all",
        "segments": _segments("chorus", 12.0),
    }

    selected, metadata = _select_authoritative_sections(songformer, all_in_one)

    assert selected == _segments("verse", 10.0)
    assert metadata["source"] == "songformer_functional_segments"
    assert metadata["segment_source"] == "songformer_functional_segment"
    assert metadata["fallback_used"] is False
    assert metadata["all_in_one_segment_count_for_audit"] == 2


def test_all_in_one_is_only_an_explicit_fallback(monkeypatch) -> None:
    monkeypatch.setenv("SECTION_FALLBACK_ALL_IN_ONE", "true")
    all_in_one = {
        "engine": "all_in_one:harmonix-all",
        "segments": _segments("chorus", 12.0),
    }

    selected, metadata = _select_authoritative_sections(
        None,
        all_in_one,
        songformer_error="runtime unavailable",
    )

    assert selected == _segments("chorus", 12.0)
    assert metadata["source"] == "all_in_one_fallback_functional_segments"
    assert metadata["fallback_used"] is True
    assert metadata["songformer_error"] == "runtime unavailable"


def test_songformer_failure_does_not_use_fallback_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SECTION_FALLBACK_ALL_IN_ONE", "false")

    selected, metadata = _select_authoritative_sections(
        None,
        {"segments": _segments("chorus", 12.0)},
        songformer_error="runtime unavailable",
    )

    assert selected == []
    assert metadata["source"] == "songformer_unavailable"
    assert metadata["fallback_policy"] == "disabled"


def test_manifest_adapter_selects_the_requested_audio(tmp_path: Path) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"not-decoded-in-this-test")
    other = tmp_path / "other.wav"
    manifest = {
        "model": "ASLP-lab/SongFormer",
        "pipeline": "MusicFM+MuQ",
        "device": "cpu",
        "frame_rate": 8.333,
        "tracks": [
            {"audio_path": str(other), "segments": _segments("chorus", 12.0)},
            {"audio_path": str(audio), "segments": _segments("verse", 10.0)},
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    payload = _songformer_payload_from_output(tmp_path, audio, "")

    assert payload["segments"] == _segments("verse", 10.0)
    assert payload["model"] == "ASLP-lab/SongFormer"


def test_configured_songformer_command_replaces_placeholders(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio = tmp_path / "song with spaces.wav"
    output = tmp_path / "output"
    monkeypatch.setenv(
        "SECTION_SONGFORMER_COMMAND",
        'python worker.py --audio "{audio}" --output-dir "{output_dir}"',
    )

    command = _songformer_command(audio, output)

    assert command == [
        "python",
        "worker.py",
        "--audio",
        str(audio),
        "--output-dir",
        str(output),
    ]
