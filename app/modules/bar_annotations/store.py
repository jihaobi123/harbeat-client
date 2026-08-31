"""Per-user, revisioned and atomic storage for public Pilot annotations."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile

from filelock import FileLock, Timeout

from app.modules.bar_annotations.schemas import AnnotationRecord, StoredAnnotationSet


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class RevisionConflict(RuntimeError):
    """The client attempted to overwrite a newer annotation revision."""


class TimelineConflict(RuntimeError):
    """The Bar timeline changed inside an existing Dataset Version."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_id(value: str, field_name: str) -> str:
    if not SAFE_ID.fullmatch(str(value or "")):
        raise ValueError(f"invalid {field_name}: {value!r}")
    return str(value)


def _user_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("user_id must be a positive integer")
    return value


class AnnotationStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path_for(self, dataset_version: str, user_id: int, track_id: str) -> Path:
        dataset = _safe_id(dataset_version, "dataset_version")
        user = _user_id(user_id)
        track = _safe_id(track_id, "track_id")
        return self.root / dataset / "users" / str(user) / f"{track}.json"

    def load(self, dataset_version: str, user_id: int, track_id: str) -> StoredAnnotationSet:
        target = self.path_for(dataset_version, user_id, track_id)
        expected_annotator = f"user:{user_id}"
        if not target.is_file():
            return StoredAnnotationSet(
                dataset_version=dataset_version,
                track_id=track_id,
                annotator_id=expected_annotator,
            )
        stored = StoredAnnotationSet.model_validate_json(target.read_text(encoding="utf-8"))
        if stored.annotator_id != expected_annotator:
            raise ValueError("stored annotator_id does not match user directory")
        return stored

    def save(
        self,
        dataset_version: str,
        user_id: int,
        track_id: str,
        expected_revision: int,
        timeline_fingerprint: str,
        annotations: list[AnnotationRecord],
        annotator_id: str,
    ) -> StoredAnnotationSet:
        expected_annotator = f"user:{_user_id(user_id)}"
        if annotator_id != expected_annotator:
            raise ValueError("annotator_id does not match authenticated user")
        if any(record.annotator_id != expected_annotator for record in annotations):
            raise ValueError("annotation record annotator_id does not match authenticated user")

        target = self.path_for(dataset_version, user_id, track_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(target.with_suffix(f"{target.suffix}.lock")), timeout=0)
        try:
            with lock:
                current = self.load(dataset_version, user_id, track_id)
                if current.revision != expected_revision:
                    raise RevisionConflict(
                        f"expected revision {expected_revision}, current revision is {current.revision}"
                    )
                if (
                    current.timeline_fingerprint
                    and current.timeline_fingerprint != timeline_fingerprint
                ):
                    raise TimelineConflict(
                        "timeline changed; create a new Dataset Version before saving"
                    )

                saved = StoredAnnotationSet(
                    dataset_version=dataset_version,
                    track_id=track_id,
                    annotator_id=expected_annotator,
                    timeline_fingerprint=timeline_fingerprint,
                    revision=current.revision + 1,
                    annotations=annotations,
                    updated_at=_utc_now(),
                )
                payload = json.dumps(
                    saved.model_dump(mode="json"), ensure_ascii=False, indent=2
                ) + "\n"
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=target.parent,
                    prefix=f".{target.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    temporary = Path(handle.name)
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.replace(temporary, target)
                finally:
                    if temporary.exists():
                        temporary.unlink()
        except Timeout as exc:
            raise RevisionConflict(
                "another annotation save is in progress; reload before saving"
            ) from exc
        return saved
