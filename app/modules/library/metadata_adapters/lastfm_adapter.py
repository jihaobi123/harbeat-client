"""Last.fm adapter scaffold for genre/style tags."""
from __future__ import annotations

import os

from .base import MetadataAdapter, MetadataTagEvidence


class LastfmAdapter(MetadataAdapter):
    source = "lastfm"

    def enabled(self) -> bool:
        return bool(os.getenv("LASTFM_API_KEY", "").strip())

    def fetch(self, *, title: str, artist: str) -> MetadataTagEvidence | None:
        api_key = os.getenv("LASTFM_API_KEY", "").strip()
        if not api_key or not title:
            return None
        try:
            import httpx

            params = {
                "method": "track.gettoptags",
                "api_key": api_key,
                "format": "json",
                "track": title,
                "artist": artist or "",
                "autocorrect": "1",
            }
            resp = httpx.get("https://ws.audioscrobbler.com/2.0/", params=params, timeout=8.0)
            resp.raise_for_status()
            tags = resp.json().get("toptags", {}).get("tag", []) or []
        except Exception:
            return None
        labels = [str(t.get("name", "")).strip() for t in tags[:12] if t.get("name")]
        if not labels:
            return None
        counts = [float(t.get("count", 0) or 0) for t in tags[:12]]
        confidence = 0.60 if not counts or max(counts) <= 0 else min(0.85, 0.45 + max(counts) / 200.0)
        return MetadataTagEvidence(
            source=self.source,
            labels=labels,
            confidence=confidence,
            raw={"top_tags": tags[:12]},
        )
