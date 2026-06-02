"""Discogs adapter scaffold.

The existing genre classifier already performs Discogs enrichment when a token
is configured. This adapter exposes the same evidence shape expected by the
new style picker cache so future refresh jobs can use one contract.
"""
from __future__ import annotations

import os

from .base import MetadataAdapter, MetadataTagEvidence


class DiscogsAdapter(MetadataAdapter):
    source = "discogs"

    def enabled(self) -> bool:
        return bool(os.getenv("DISCOGS_USER_TOKEN", "").strip())

    def fetch(self, *, title: str, artist: str) -> MetadataTagEvidence | None:
        if not self.enabled():
            return None
        try:
            from app.modules.library.genre_classifier import _enrich_from_discogs

            result = _enrich_from_discogs(title, artist)
        except Exception:
            return None
        if not result:
            return None
        labels = list(result.get("discogs_labels_raw") or [])
        if not labels:
            labels = [g.get("name", "") for g in result.get("genres") or []]
        labels = [str(v).strip() for v in labels if str(v).strip()]
        if not labels:
            return None
        confidence = max(
            [float(g.get("confidence", 0.0) or 0.0) for g in result.get("genres") or []]
            or [0.65]
        )
        return MetadataTagEvidence(
            source=self.source,
            labels=labels,
            confidence=min(1.0, confidence),
            raw={k: v for k, v in result.items() if k not in {"discogs_labels_raw"}},
        )

