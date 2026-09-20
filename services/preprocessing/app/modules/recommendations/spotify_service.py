"""Spotify search service — ported from FinalReco (commit 1d65a9dc).

Uses spotipy client-credentials flow for search, OAuth for playlist access.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

_MARKET = "US"
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 10  # Spotify client-credentials cap
_PLAYLIST_SCOPE = "playlist-read-private playlist-read-collaborative"


def _client_id() -> str:
    return os.getenv("SPOTIPY_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()


def _redirect_uri() -> str:
    return os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback").strip()


def _get_client():
    """Lazy import + create spotipy client (client-credentials, no user auth)."""
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials

    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=_client_id(),
            client_secret=_client_secret(),
        )
    )


def _get_playlist_client():
    """Lazy import + create spotipy client with OAuth for playlist reading.

    Requires SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and SPOTIPY_REDIRECT_URI
    to be set. First call requires browser-based OAuth consent.
    """
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=_client_id(),
            client_secret=_client_secret(),
            redirect_uri=_redirect_uri(),
            scope=_PLAYLIST_SCOPE,
            open_browser=False,
        )
    )


def search_tracks(query: str, limit: int = _DEFAULT_LIMIT) -> List[dict]:
    """Search Spotify and return normalised track dicts."""
    if not _client_id() or not _client_secret():
        logger.warning("Spotify credentials not configured, returning empty results")
        return []

    # Spotify client-credentials flow caps at 10 results per request
    safe_limit = max(1, min(int(limit), _MAX_LIMIT))

    try:
        sp = _get_client()
        logger.info("Spotify search: q=%r, limit=%d", query, safe_limit)
        raw = (
            sp.search(q=str(query), type="track", market=_MARKET, limit=safe_limit)
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


# ── Track lookup & playlist import (ported from FinalReco) ──────────


def get_track_by_id(track_id: str) -> Optional[dict]:
    """Fetch a single Spotify track by its ID."""
    if not track_id:
        return None
    sp = _get_client()
    try:
        return sp.track(track_id)
    except Exception:
        return None


def parse_playlist_id(playlist_input: str) -> str:
    """Extract Spotify playlist ID from URL, URI, or raw ID."""
    value = str(playlist_input or "").strip()
    if "playlist/" in value:
        return value.split("playlist/")[-1].split("?")[0].strip()
    if value.startswith("spotify:playlist:"):
        return value.split(":")[-1].strip()
    return value


def fetch_playlist_tracks(playlist_input: str) -> List[dict]:
    """Fetch all tracks from a Spotify playlist (handles pagination).

    Requires SPOTIPY_REDIRECT_URI and OAuth consent on first use.
    """
    playlist_id = parse_playlist_id(playlist_input)
    sp = _get_playlist_client()
    results = sp.playlist_items(playlist_id)
    rows: List[dict] = []

    while True:
        for item in results.get("items", []):
            track = item.get("track") or item.get("item") or {}
            if not track or track.get("is_local") or not track.get("id"):
                continue
            rows.append(track)

        if not results.get("next"):
            break
        results = sp.next(results)

    return rows
