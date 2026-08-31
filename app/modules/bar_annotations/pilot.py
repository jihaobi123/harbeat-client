"""Strict configuration for the shared public annotation Pilot."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class PilotManifestError(ValueError):
    """The Pilot manifest is malformed or unsafe."""


class PilotTrackNotFound(LookupError):
    """A track is not part of the public Pilot."""


@dataclass(frozen=True)
class PilotManifest:
    dataset_version: str
    track_ids: tuple[str, ...]

    @classmethod
    def load(cls, path: str | Path) -> "PilotManifest":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PilotManifestError("Pilot manifest could not be read") from exc
        if not isinstance(payload, dict) or set(payload) != {"dataset_version", "track_ids"}:
            raise PilotManifestError("Pilot manifest fields are invalid")
        dataset_version = payload["dataset_version"]
        track_ids = payload["track_ids"]
        if not isinstance(dataset_version, str) or not SAFE_ID.fullmatch(dataset_version):
            raise PilotManifestError("Pilot dataset_version is invalid")
        if not isinstance(track_ids, list) or not track_ids:
            raise PilotManifestError("Pilot track_ids must be a non-empty list")
        if any(not isinstance(item, str) or not SAFE_ID.fullmatch(item) for item in track_ids):
            raise PilotManifestError("Pilot track_id is invalid")
        if len(set(track_ids)) != len(track_ids):
            raise PilotManifestError("Pilot track_ids cannot contain duplicates")
        return cls(dataset_version=dataset_version, track_ids=tuple(track_ids))

    def require_track(self, track_id: str) -> str:
        if track_id not in self.track_ids:
            raise PilotTrackNotFound("Pilot track not found")
        return track_id
