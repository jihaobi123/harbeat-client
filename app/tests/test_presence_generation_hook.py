from types import SimpleNamespace

from app.modules.annotations import service as annotation_service


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
