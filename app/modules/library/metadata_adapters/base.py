"""Shared adapter contracts for external music metadata evidence."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MetadataTagEvidence:
    source: str
    labels: list[str]
    label_type: str = "genre_style"
    confidence: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def as_genre_profile_source(self) -> dict[str, Any]:
        return {
            "labels": list(dict.fromkeys(self.labels)),
            "label_type": self.label_type,
            "confidence": max(0.0, min(1.0, float(self.confidence or 0.0))),
            "raw": self.raw or {},
        }


class MetadataAdapter:
    source: str = "unknown"

    def enabled(self) -> bool:
        return False

    def fetch(self, *, title: str, artist: str) -> MetadataTagEvidence | None:
        """Return cached-ready tag evidence or ``None`` when disabled/empty.

        Implementations must never raise for missing credentials. They are not
        called from DJ Control's live style picker.
        """
        return None

