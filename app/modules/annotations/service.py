"""Application service for generating and reviewing presence annotations."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from app.modules.annotations.schemas import (
    CandidateSnapshot,
    PresenceAnnotationBundle,
    PresenceReviewRequest,
    TimelineSnapshot,
)
from app.modules.annotations.store import AnnotationStore
from app.modules.library.bar_timeline import TimelineError, build_bar_timeline
from app.modules.library.presence_analysis import (
    CANDIDATE_VERSION,
    PresenceAnalysisError,
    THRESHOLD_VERSION,
    analyze_bar_presence,
)
from app.shared.config import get_settings


DATASET_VERSION = "bar-presence-pilot-1.0.0"
TIMELINE_VERSION = "bar_timeline@0.1.0"


class AnnotationAccessError(PermissionError):
    pass


class AnnotationGenerationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PresenceAnnotationService:
    def __init__(self, store: AnnotationStore):
        self.store = store

    @classmethod
    def from_settings(cls) -> "PresenceAnnotationService":
        return cls(AnnotationStore(get_settings().annotation_dir))

    @staticmethod
    def _check_access(song: Any, requesting_user_id: int) -> None:
        if int(getattr(song, "user_id", 0)) != int(requesting_user_id):
            raise AnnotationAccessError("song does not belong to the current user")

    def generate_for_song(
        self,
        *,
        song: Any,
        requesting_user_id: int,
    ) -> PresenceAnnotationBundle:
        self._check_access(song, requesting_user_id)
        stems = getattr(song, "stems", None)
        if not stems:
            raise AnnotationGenerationError(
                "stems_unavailable",
                "no separated Stems are available for this song",
            )
        try:
            timeline = build_bar_timeline(
                downbeats=getattr(song, "downbeats", []) or [],
                beat_points=getattr(song, "beat_points", []) or [],
                duration=float(getattr(song, "duration", 0.0) or 0.0),
                time_signature=getattr(song, "time_signature", {}) or {},
                beat_confidence=getattr(song, "beat_confidence", None),
                beat_needs_review=bool(getattr(song, "beat_needs_review", False)),
            )
            analysis = analyze_bar_presence(stems, timeline.bars)
        except (TimelineError, PresenceAnalysisError) as exc:
            code = getattr(exc, "code", "presence_analysis_failed")
            raise AnnotationGenerationError(code, str(exc)) from exc

        now = datetime.now(timezone.utc)
        bundle = PresenceAnnotationBundle(
            schema_name="harbeat.presence_annotation_bundle",
            schema_version="1.0.0",
            dataset_version=DATASET_VERSION,
            track_id=str(song.id),
            user_id=int(song.user_id),
            timeline=TimelineSnapshot(
                source=timeline.source,
                meter_numerator=timeline.meter_numerator,
                confidence=timeline.confidence,
                version=TIMELINE_VERSION,
                bars=[asdict(bar) for bar in timeline.bars],
            ),
            candidate_source=analysis.get("candidate_source", CANDIDATE_VERSION),
            threshold_version=analysis.get("threshold_version", THRESHOLD_VERSION),
            revision=1,
            candidates=CandidateSnapshot(
                sample_rate=analysis.get("sample_rate"),
                elements=analysis["elements"],
            ),
            revisions=[],
            created_at=now,
            updated_at=now,
        )
        return self.store.create_candidates(
            user_id=requesting_user_id,
            bundle=bundle,
        )

    def read(self, *, song: Any, requesting_user_id: int) -> PresenceAnnotationBundle:
        self._check_access(song, requesting_user_id)
        return self.store.read(user_id=requesting_user_id, track_id=str(song.id))

    def review(
        self,
        *,
        song: Any,
        requesting_user_id: int,
        payload: PresenceReviewRequest,
        actor_id: str,
    ) -> PresenceAnnotationBundle:
        self._check_access(song, requesting_user_id)
        return self.store.save_review(
            user_id=requesting_user_id,
            track_id=str(song.id),
            expected_revision=payload.expected_revision,
            actor_id=actor_id,
            elements=payload.elements,
        )

    def adjudicate(
        self,
        *,
        song: Any,
        requesting_user_id: int,
        payload: PresenceReviewRequest,
        actor_id: str,
    ) -> PresenceAnnotationBundle:
        self._check_access(song, requesting_user_id)
        return self.store.save_adjudication(
            user_id=requesting_user_id,
            track_id=str(song.id),
            expected_revision=payload.expected_revision,
            actor_id=actor_id,
            elements=payload.elements,
        )

    def export(self, *, song: Any, requesting_user_id: int) -> str:
        bundle = self.read(song=song, requesting_user_id=requesting_user_id)
        return self.store.export_reviewed_jsonl(bundle)


def try_generate_presence_candidates(song: Any) -> dict[str, Any]:
    try:
        bundle = PresenceAnnotationService.from_settings().generate_for_song(
            song=song,
            requesting_user_id=int(song.user_id),
        )
        return {"status": "candidate", "revision": bundle.revision}
    except (AnnotationGenerationError, TimelineError, PresenceAnalysisError) as exc:
        return {
            "status": "needs_review",
            "code": getattr(exc, "code", "presence_analysis_failed"),
            "error": str(exc),
        }

