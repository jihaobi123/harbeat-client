"""MusicBrainz adapter scaffold.

MusicBrainz genre/style coverage is inconsistent, so this first version
only enables the adapter when explicitly configured and returns labels from
recording tags when available.
"""
from __future__ import annotations

import os

from .base import MetadataAdapter, MetadataTagEvidence


class MusicBrainzAdapter(MetadataAdapter):
    source = "musicbrainz"

    def enabled(self) -> bool:
        return bool(os.getenv("MUSICBRAINZ_APP_NAME", "").strip())

    def fetch(self, *, title: str, artist: str) -> MetadataTagEvidence | None:
        app_name = os.getenv("MUSICBRAINZ_APP_NAME", "").strip()
        if not app_name or not title:
            return None
        query = f'recording:"{title}"'
        if artist:
            query += f' AND artist:"{artist}"'
        try:
            import httpx

            headers = {"User-Agent": f"{app_name}/1.0 (harbeat-client)"}
            resp = httpx.get(
                "https://musicbrainz.org/ws/2/recording",
                params={"query": query, "fmt": "json", "limit": "3"},
                headers=headers,
                timeout=8.0,
            )
            resp.raise_for_status()
            recordings = resp.json().get("recordings") or []
        except Exception:
            return None
        labels: list[str] = []
        for rec in recordings[:3]:
            for tag in rec.get("tags") or []:
                name = str(tag.get("name", "")).strip()
                if name:
                    labels.append(name)
        labels = list(dict.fromkeys(labels))
        if not labels:
            return None
        return MetadataTagEvidence(
            source=self.source,
            labels=labels[:12],
            confidence=0.55,
            raw={"recording_count": len(recordings)},
        )
