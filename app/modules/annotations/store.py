"""Atomic file storage for candidate and human annotation revisions."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import tempfile
from typing import Literal

from app.modules.annotations.schemas import (
    ELEMENT_NAMES,
    ElementReview,
    PresenceAnnotationBundle,
    ReviewRevision,
)


TRACK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class AnnotationStoreError(RuntimeError):
    pass


class AnnotationNotFound(AnnotationStoreError):
    pass


class RevisionConflict(AnnotationStoreError):
    pass


class InvalidTrackId(AnnotationStoreError):
    pass


class AnnotationStore:
    def __init__(self, root_dir: str):
        self.root_dir = os.path.abspath(root_dir)

    def _path(self, user_id: int, track_id: str) -> str:
        if user_id <= 0:
            raise AnnotationStoreError("user_id must be positive")
        if not TRACK_ID_PATTERN.fullmatch(track_id):
            raise InvalidTrackId("track_id contains unsafe characters")
        return os.path.join(
            self.root_dir,
            str(user_id),
            track_id,
            "bar-presence-1.0.0.json",
        )

    def _write(self, path: str, bundle: PresenceAnnotationBundle) -> None:
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        descriptor, temp_path = tempfile.mkstemp(
            prefix=".bar-presence-",
            suffix=".tmp",
            dir=directory,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    bundle.model_dump(mode="json"),
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def create_candidates(
        self,
        *,
        user_id: int,
        bundle: PresenceAnnotationBundle,
    ) -> PresenceAnnotationBundle:
        if bundle.user_id != user_id:
            raise AnnotationStoreError("bundle user_id does not match storage owner")
        path = self._path(user_id, bundle.track_id)
        if os.path.isfile(path):
            existing = self.read(user_id=user_id, track_id=bundle.track_id)
            if (
                existing.dataset_version == bundle.dataset_version
                and existing.candidate_source == bundle.candidate_source
                and existing.timeline == bundle.timeline
            ):
                return existing
            raise RevisionConflict("candidate bundle already exists with another version")
        self._write(path, bundle)
        return bundle

    def read(self, *, user_id: int, track_id: str) -> PresenceAnnotationBundle:
        path = self._path(user_id, track_id)
        if not os.path.isfile(path):
            raise AnnotationNotFound(f"no presence annotations for {track_id}")
        with open(path, "r", encoding="utf-8") as handle:
            return PresenceAnnotationBundle.model_validate(json.load(handle))

    def _save_revision(
        self,
        *,
        user_id: int,
        track_id: str,
        expected_revision: int,
        actor_id: str,
        elements: dict,
        annotation_status: Literal["reviewed", "adjudicated"],
    ) -> PresenceAnnotationBundle:
        bundle = self.read(user_id=user_id, track_id=track_id)
        if bundle.revision != expected_revision:
            raise RevisionConflict(
                f"expected revision {expected_revision}, current revision is {bundle.revision}"
            )

        parsed = {
            element: ElementReview.model_validate(elements[element])
            for element in ELEMENT_NAMES
        }
        bar_count = len(bundle.timeline.bars)
        for review in parsed.values():
            previous_end = 0
            for item in sorted(review.ranges, key=lambda value: value.start_bar_index):
                if item.end_bar_index > bar_count:
                    raise AnnotationStoreError("review range exceeds Bar timeline")
                if item.start_bar_index < previous_end:
                    raise AnnotationStoreError("review ranges cannot overlap")
                previous_end = item.end_bar_index

        now = datetime.now(timezone.utc)
        next_revision = bundle.revision + 1
        updated = bundle.model_copy(deep=True)
        updated.revision = next_revision
        updated.updated_at = now
        updated.revisions.append(
            ReviewRevision(
                revision=next_revision,
                annotation_status=annotation_status,
                actor_id=actor_id,
                created_at=now,
                elements=parsed,
            )
        )
        self._write(self._path(user_id, track_id), updated)
        return updated

    def save_review(
        self,
        *,
        user_id: int,
        track_id: str,
        expected_revision: int,
        actor_id: str,
        elements: dict,
    ) -> PresenceAnnotationBundle:
        return self._save_revision(
            user_id=user_id,
            track_id=track_id,
            expected_revision=expected_revision,
            actor_id=actor_id,
            elements=elements,
            annotation_status="reviewed",
        )

    def save_adjudication(
        self,
        *,
        user_id: int,
        track_id: str,
        expected_revision: int,
        actor_id: str,
        elements: dict,
    ) -> PresenceAnnotationBundle:
        return self._save_revision(
            user_id=user_id,
            track_id=track_id,
            expected_revision=expected_revision,
            actor_id=actor_id,
            elements=elements,
            annotation_status="adjudicated",
        )

    @staticmethod
    def export_reviewed_jsonl(bundle: PresenceAnnotationBundle) -> str:
        if not bundle.revisions:
            return ""
        revision = bundle.revisions[-1]
        records = []
        bars = bundle.timeline.bars
        for element in ELEMENT_NAMES:
            review = revision.elements[element]
            if review.review_state != "reviewed":
                continue
            for range_index, item in enumerate(review.ranges):
                digest = hashlib.sha256(
                    f"{bundle.track_id}:{element}:{revision.revision}:{range_index}".encode("utf-8")
                ).hexdigest()[:24]
                start_bar = bars[item.start_bar_index]
                end_bar = bars[item.end_bar_index - 1]
                records.append(
                    {
                        "schema_name": "harbeat.annotation_record",
                        "schema_version": "1.0.0",
                        "annotation_id": f"ann:{digest}",
                        "dataset_version": bundle.dataset_version,
                        "track_id": bundle.track_id,
                        "task_id": f"elements.{element}.presence",
                        "granularity": "bar",
                        "start_sec": start_bar.start_sec,
                        "end_sec": end_bar.end_sec,
                        "start_bar_index": item.start_bar_index,
                        "end_bar_index": item.end_bar_index,
                        "value": True,
                        "annotator_id": revision.actor_id,
                        "annotation_status": revision.annotation_status,
                        "annotator_confidence": item.confidence,
                        "candidate_source": bundle.candidate_source,
                        "created_at": revision.created_at.isoformat().replace("+00:00", "Z"),
                    }
                )
        return "\n".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            for record in records
        )

