from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.modules.bar_annotations.songformer_sections import (
    RelabelerState,
    SongFormerSectionDocument,
    SongFormerSectionInvalid,
    SongFormerSectionStore,
    songformer_document,
)


def _document(track_id: str = "track-1") -> SongFormerSectionDocument:
    return songformer_document(
        track_id=track_id,
        audio_fingerprint="audio-sha",
        runtime_fingerprint={"runner_version": "songformer_isolated_v3"},
        cache_namespace="songformer-cache-a",
        segments=[
            {
                "start": 0.21,
                "end": 8.12,
                "label": "intro",
                "label_probabilities": {"intro": 0.8, "verse": 0.2},
                "label_confidence": 0.8,
                "label_margin": 0.6,
            },
            {
                "start": 8.12,
                "end": 16.0,
                "label": "verse",
                "label_probabilities": {"intro": 0.1, "verse": 0.9},
                "label_confidence": 0.9,
                "label_margin": 0.8,
            },
        ],
    )


def test_round_trip_preserves_boundaries_and_disabled_relabeler(tmp_path) -> None:
    store = SongFormerSectionStore(tmp_path)

    store.save(_document())
    loaded = store.load("track-1")

    assert loaded is not None
    assert loaded.segments[0].start == 0.21
    assert loaded.segments[1].end == 16.0
    assert loaded.relabeler.enabled is False
    assert loaded.relabeler.model_status == "not_installed"


def test_missing_sidecar_returns_none(tmp_path) -> None:
    assert SongFormerSectionStore(tmp_path).load("track-1") is None


def test_invalid_sidecar_fails_closed(tmp_path) -> None:
    (tmp_path / "track-1.json").write_text(
        json.dumps({"schema_name": "harbeat.songformer_sections", "segments": "bad"}),
        encoding="utf-8",
    )

    with pytest.raises(SongFormerSectionInvalid):
        SongFormerSectionStore(tmp_path).load("track-1")


def test_store_rejects_unsafe_track_id(tmp_path) -> None:
    store = SongFormerSectionStore(tmp_path)

    with pytest.raises(SongFormerSectionInvalid):
        store.load("../../annotations")


def test_document_rejects_overlapping_segments() -> None:
    with pytest.raises(ValidationError, match="overlap"):
        songformer_document(
            track_id="track-1",
            audio_fingerprint="audio-sha",
            runtime_fingerprint={"runner_version": "v3"},
            segments=[
                {"start": 0.0, "end": 8.0, "label": "intro"},
                {"start": 7.5, "end": 12.0, "label": "verse"},
            ],
        )


def test_document_rejects_enabled_residual_classifier() -> None:
    with pytest.raises(ValidationError):
        RelabelerState.model_validate(
            {
                "enabled": True,
                "mode": "active",
                "model_status": "ready",
                "model_version": "classifier-v1",
            }
        )


def test_failed_document_keeps_error_without_segments() -> None:
    document = songformer_document(
        track_id="track-1",
        audio_fingerprint="audio-sha",
        runtime_fingerprint={"runner_version": "v3"},
        segments=[],
        status="failed",
        error="RuntimeError: model failed",
    )

    assert document.status == "failed"
    assert document.segments == []
    assert document.error == "RuntimeError: model failed"


def test_ready_document_requires_segments() -> None:
    with pytest.raises(ValidationError, match="ready document requires segments"):
        songformer_document(
            track_id="track-1",
            audio_fingerprint="audio-sha",
            runtime_fingerprint={"runner_version": "v3"},
            segments=[],
        )
