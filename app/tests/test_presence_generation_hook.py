from types import SimpleNamespace

from app.modules.annotations import service as annotation_service
from app.modules.library.analysis_persistence import apply_analysis_result


class _FailingService:
    def generate_for_song(self, **_kwargs):
        raise RuntimeError("bad timeline")


class _SuccessfulService:
    def generate_for_song(self, **_kwargs):
        return SimpleNamespace(revision=3)


def test_generation_hook_is_non_fatal_for_unexpected_errors(monkeypatch):
    monkeypatch.setattr(
        annotation_service.PresenceAnnotationService,
        "from_settings",
        classmethod(lambda cls: _FailingService()),
    )

    result = annotation_service.try_generate_presence_candidates(
        SimpleNamespace(id="track-1", user_id=7)
    )

    assert result == {
        "status": "needs_review",
        "code": "presence_analysis_failed",
        "error": "bad timeline",
    }


def test_generation_hook_returns_created_revision(monkeypatch):
    monkeypatch.setattr(
        annotation_service.PresenceAnnotationService,
        "from_settings",
        classmethod(lambda cls: _SuccessfulService()),
    )

    result = annotation_service.try_generate_presence_candidates(
        SimpleNamespace(id="track-1", user_id=7)
    )

    assert result == {"status": "candidate", "revision": 3}


def test_rq_analysis_persists_timeline_quality_fields_needed_by_presence():
    song = SimpleNamespace()

    apply_analysis_result(song, {
        "bpm": 120.0,
        "duration": 8.0,
        "beat_confidence": 0.91,
        "beat_confidence_details": {"agreement": 0.9},
        "beat_grid_offset": 0.1,
        "beat_grid_interval": 0.5,
        "beat_engines_used": ["librosa"],
        "beat_needs_review": False,
        "time_signature": {"numerator": 4, "denominator": 4, "confidence": 0.88},
        "downbeats": [0.1, 2.1, 4.1, 6.1],
    })

    assert song.beat_confidence == 0.91
    assert song.beat_needs_review == 0
    assert song.time_signature["numerator"] == 4
    assert song.downbeats == [0.1, 2.1, 4.1, 6.1]
