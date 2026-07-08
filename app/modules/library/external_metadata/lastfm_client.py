"""Last.fm client for track and artist top tags."""
from __future__ import annotations

import httpx

from app.modules.library.external_metadata.schemas import ExternalSourceResult
from app.shared.config import get_settings


async def fetch_lastfm_metadata(
    *,
    title: str,
    artist: str,
    timeout_sec: float = 8.0,
) -> ExternalSourceResult:
    settings = get_settings()
    api_key = settings.lastfm_api_key.strip()
    if not api_key:
        return ExternalSourceResult.disabled("lastfm")
    if not title and not artist:
        return ExternalSourceResult.miss("lastfm")
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            track_tags = []
            if title and artist:
                resp = await client.get(
                    "https://ws.audioscrobbler.com/2.0/",
                    params={
                        "method": "track.getTopTags",
                        "artist": artist,
                        "track": title,
                        "api_key": api_key,
                        "format": "json",
                        "autocorrect": "1",
                    },
                )
                resp.raise_for_status()
                track_tags = resp.json().get("toptags", {}).get("tag", []) or []

            artist_tags = []
            if not track_tags and artist:
                resp = await client.get(
                    "https://ws.audioscrobbler.com/2.0/",
                    params={
                        "method": "artist.getTopTags",
                        "artist": artist,
                        "api_key": api_key,
                        "format": "json",
                        "autocorrect": "1",
                    },
                )
                resp.raise_for_status()
                artist_tags = resp.json().get("toptags", {}).get("tag", []) or []

            tags = track_tags or artist_tags
            labels = [str(t.get("name")) for t in tags[:16] if t.get("name")]
            if not labels:
                return ExternalSourceResult.miss("lastfm")
            counts = [float(t.get("count", 0) or 0) for t in tags[:16]]
            confidence = 0.62 if not counts or max(counts) <= 0 else min(0.85, 0.50 + max(counts) / 250.0)
            return ExternalSourceResult(
                source="lastfm",
                status="hit",
                labels=labels,
                confidence=confidence,
                matched_title=title,
                matched_artist=artist,
                raw={
                    "raw_count": len(tags),
                    "track_tags": track_tags[:12],
                    "artist_tags": artist_tags[:12],
                    "fallback": bool(artist_tags and not track_tags),
                },
            )
    except Exception as exc:
        return ExternalSourceResult.error_result("lastfm", str(exc))

