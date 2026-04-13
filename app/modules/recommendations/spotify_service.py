"""Spotify search service — ported from FinalReco (commit 1d65a9dc).

Uses spotipy client-credentials flow (no user auth needed).
"""
from __future__ import annotations

import logging
import os
from typing import List

logger = logging.getLogger(__name__)

_MARKET = "US"
_DEFAULT_LIMIT = 10


def _client_id() -> str:
    return os.getenv("SPOTIPY_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()


def _get_client():
    """Lazy import + create spotipy client."""
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials

    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=_client_id(),
            client_secret=_client_secret(),
        )
    )


def search_tracks(query: str, limit: int = _DEFAULT_LIMIT) -> List[dict]:
    """Search Spotify and return normalised track dicts."""
    if not _client_id() or not _client_secret():
        logger.warning("Spotify credentials not configured, returning empty results")
        return []

    try:
        sp = _get_client()
        raw = (
            sp.search(q=str(query), type="track", market=_MARKET, limit=limit)
            .get("tracks", {})
            .get("items", [])
        )
    except Exception as exc:
        logger.error("Spotify search failed: %s", exc)
        return []

    results: List[dict] = []
    for item in raw:
        artists = ", ".join(a.get("name", "") for a in (item.get("artists") or []))
        album = item.get("album") or {}
        images = album.get("images") or []
        results.append({
            "title": item.get("name", ""),
            "artist": artists,
            "spotify_id": item.get("id"),
            "preview_url": item.get("preview_url"),
            "album_art": images[0]["url"] if images else None,
            "spotify_url": (item.get("external_urls") or {}).get("spotify"),
        })

    return results
