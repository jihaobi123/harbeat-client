"""Spotify search integration for vibe search.

Uses spotipy client credentials flow (no user login needed).
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

_sp_client = None


def _get_client():
    global _sp_client
    if _sp_client is not None:
        return _sp_client
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
    except ImportError:
        logger.warning("spotipy not installed — Spotify search disabled")
        return None

    client_id = os.getenv("SPOTIPY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        logger.warning("SPOTIPY_CLIENT_ID/SECRET not set — Spotify search disabled")
        return None

    try:
        _sp_client = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret,
            )
        )
        return _sp_client
    except Exception:
        logger.exception("Failed to init Spotify client")
        return None


def search_tracks(search_query: str, limit: int = 10) -> List[dict]:
    """Search Spotify and return normalized track dicts."""
    sp = _get_client()
    if sp is None:
        return []

    try:
        results = sp.search(q=search_query, type="track", market="US", limit=limit)
        items = results.get("tracks", {}).get("items", [])
    except Exception:
        logger.exception("Spotify search failed for query: %s", search_query)
        return []

    tracks = []
    for item in items:
        if not item or not item.get("id"):
            continue
        artists = ", ".join(
            a.get("name", "") for a in (item.get("artists") or []) if a.get("name")
        ) or "Unknown Artist"
        album_images = item.get("album", {}).get("images", [])
        album_art = album_images[0]["url"] if album_images else None
        tracks.append({
            "spotify_id": item["id"],
            "title": item.get("name", "Unknown"),
            "artist": artists,
            "preview_url": item.get("preview_url"),
            "album_art": album_art,
            "spotify_url": item.get("external_urls", {}).get("spotify"),
        })
    return tracks
