import os
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth

from services.config import PLAYLIST_SCOPE, SPOTIFY_SEARCH_LIMIT


_def_market = "US"


def _client_id() -> str:
    return os.getenv("SPOTIPY_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()


def _redirect_uri() -> str:
    return os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback").strip()


def get_app_client() -> spotipy.Spotify:
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=_client_id(),
            client_secret=_client_secret(),
        )
    )


def get_playlist_client() -> spotipy.Spotify:
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=_client_id(),
            client_secret=_client_secret(),
            redirect_uri=_redirect_uri(),
            scope=PLAYLIST_SCOPE,
            open_browser=False,
        )
    )


def search_tracks(search_query: str, limit: int = SPOTIFY_SEARCH_LIMIT):
    sp = get_app_client()
    return sp.search(q=str(search_query), type="track", market=_def_market, limit=limit).get("tracks", {}).get("items", [])


def get_track_by_id(track_id: str) -> Optional[dict]:
    if not track_id:
        return None
    sp = get_app_client()
    try:
        return sp.track(track_id)
    except Exception:
        return None


def parse_playlist_id(playlist_input: str) -> str:
    value = str(playlist_input or "").strip()
    if "playlist/" in value:
        return value.split("playlist/")[-1].split("?")[0].strip()
    if value.startswith("spotify:playlist:"):
        return value.split(":")[-1].strip()
    return value


def fetch_playlist_tracks(playlist_input: str):
    playlist_id = parse_playlist_id(playlist_input)
    sp = get_playlist_client()
    results = sp.playlist_items(playlist_id)
    rows = []

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
