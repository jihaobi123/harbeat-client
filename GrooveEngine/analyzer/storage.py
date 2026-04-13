"""Persistence helpers for analyzer metadata."""

from __future__ import annotations

import json
from pathlib import Path

from core.datatypes import TrackMetadata


class MetadataStorage:
    """Reads and writes track metadata JSON files."""

    @staticmethod
    def save(metadata: TrackMetadata, output_path: str | Path) -> Path:
        """Persist metadata to disk using the strict schema."""

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
        return path

    @staticmethod
    def load(input_path: str | Path) -> TrackMetadata:
        """Load metadata from disk into a validated model."""

        path = Path(input_path)
        return TrackMetadata.model_validate(json.loads(path.read_text(encoding="utf-8")))
