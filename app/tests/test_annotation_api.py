from pathlib import Path
from types import SimpleNamespace
import importlib.util
import os
import sys
import types

import numpy as np
import pytest
import soundfile as sf
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

if importlib.util.find_spec("jwt") is None:
    jwt_stub = types.ModuleType("jwt")
    jwt_stub.ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})
    jwt_stub.InvalidTokenError = type("InvalidTokenError", (Exception,), {})
    jwt_stub.encode = lambda *args, **kwargs: "test-token"
    jwt_stub.decode = lambda *args, **kwargs: {"sub": "7", "type": "access"}
    sys.modules["jwt"] = jwt_stub

from app.modules.annotations import router as annotation_router
from app.modules.annotations.router import generate_presence_endpoint
from app.modules.annotations.service import (
    AnnotationAccessError,
    PresenceAnnotationService,
)
from app.modules.annotations.store import AnnotationStore


def _song(tmp_path: Path, user_id: int = 7):
    sample_rate = 1000
    duration = 4
    time = np.arange(sample_rate * duration) / sample_rate
    paths = {}
    for name, frequency in {
        "vocals": 220,
        "drums": 5,
        "bass": 60,
        "other": 330,
    }.items():
        audio = (0.25 * np.sin(2 * np.pi * frequency * time)).astype(np.float32)
        path = tmp_path / f"{name}.wav"
        sf.write(path, audio, sample_rate)
        paths[name] = str(path)
    return SimpleNamespace(
        id="track-1",
        user_id=user_id,
        duration=float(duration),
        downbeats=[0.0, 2.0],
        beat_points=[i * 0.5 for i in range(8)],
        time_signature={"numerator": 4, "denominator": 4, "confidence": 0.9},
        beat_confidence=0.95,
        beat_needs_review=False,
        stems=paths,
    )


class _FakeDb:
    def __init__(self, song):
        self.song = song

    def get(self, _model, song_id):
        return self.song if self.song.id == song_id else None


def test_generate_candidates_uses_owned_song(tmp_path: Path):
    song = _song(tmp_path)
    service = PresenceAnnotationService(
        AnnotationStore(str(tmp_path / "annotations"))
    )

    bundle = service.generate_for_song(song=song, requesting_user_id=7)

    assert bundle.track_id == song.id
    assert bundle.timeline.source == "downbeats"
    assert bundle.candidate_source == "method:bar_presence_candidate@0.1.0"
    assert set(bundle.candidates.elements) == {"vocal", "drums", "bass", "melody"}


def test_generate_candidates_rejects_other_users_song(tmp_path: Path):
    song = _song(tmp_path, user_id=8)
    service = PresenceAnnotationService(
        AnnotationStore(str(tmp_path / "annotations"))
    )

    with pytest.raises(AnnotationAccessError):
        service.generate_for_song(song=song, requesting_user_id=7)


def test_generate_endpoint_uses_authenticated_user(tmp_path: Path, monkeypatch):
    song = _song(tmp_path)
    service = PresenceAnnotationService(
        AnnotationStore(str(tmp_path / "annotations"))
    )
    monkeypatch.setattr(annotation_router, "_library_song_model", lambda: object)

    response = generate_presence_endpoint(
        song_id=song.id,
        db=_FakeDb(song),
        current_user=SimpleNamespace(id=7),
        service=service,
    )

    assert response.data.user_id == 7
    assert response.data.track_id == "track-1"


def test_generate_endpoint_rejects_foreign_song(tmp_path: Path, monkeypatch):
    song = _song(tmp_path, user_id=8)
    service = PresenceAnnotationService(
        AnnotationStore(str(tmp_path / "annotations"))
    )
    monkeypatch.setattr(annotation_router, "_library_song_model", lambda: object)

    with pytest.raises(HTTPException) as exc_info:
        generate_presence_endpoint(
            song_id=song.id,
            db=_FakeDb(song),
            current_user=SimpleNamespace(id=7),
            service=service,
        )

    assert exc_info.value.status_code == 403
