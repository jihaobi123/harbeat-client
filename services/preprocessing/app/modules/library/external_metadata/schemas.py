"""Data shapes for external metadata enrichment."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.modules.library.external_metadata.normalizer import normalize_labels


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class ExternalSourceResult:
    source: str
    status: str
    labels: list[str] = field(default_factory=list)
    confidence: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    mbid: str | None = None
    release_id: int | None = None
    matched_title: str | None = None
    matched_artist: str | None = None
    needs_review: bool = False
    error: str | None = None
    fetched_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def disabled(cls, source: str, reason: str = "missing_credentials") -> "ExternalSourceResult":
        return cls(source=source, status="disabled", error=reason)

    @classmethod
    def miss(cls, source: str) -> "ExternalSourceResult":
        return cls(source=source, status="miss")

    @classmethod
    def error_result(cls, source: str, message: str) -> "ExternalSourceResult":
        return cls(source=source, status="error", error=message[:200])

    def normalized_labels(self) -> list[str]:
        return normalize_labels(self.labels)

    def as_genre_profile_source(self) -> dict[str, Any]:
        data = {
            "status": self.status,
            "labels": self.normalized_labels(),
            "raw_labels": list(dict.fromkeys([str(v) for v in self.labels if str(v).strip()])),
            "confidence": max(0.0, min(1.0, float(self.confidence or 0.0))),
            "fetched_at": self.fetched_at,
        }
        if self.raw:
            data["raw"] = self.raw
        if self.mbid:
            data["mbid"] = self.mbid
        if self.release_id:
            data["release_id"] = self.release_id
        if self.matched_title:
            data["matched_title"] = self.matched_title
        if self.matched_artist:
            data["matched_artist"] = self.matched_artist
        if self.needs_review:
            data["needs_review"] = True
        if self.error:
            data["error"] = self.error
        return data


@dataclass
class ExternalEnrichmentResult:
    song_id: str
    sources: dict[str, ExternalSourceResult]
    style_evidence: dict[str, dict]
    dance_style_scores: dict[str, float]
    status: str

    def source_statuses(self) -> dict[str, str]:
        return {k: v.status for k, v in self.sources.items()}

