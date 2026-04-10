import os

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyClientCredentials


load_dotenv()

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET")
))


def _sanitize_query(search_query: str) -> str:
    query = str(search_query or "").strip().lower()
    tokens = query.split()
    keep = [token for token in tokens if token.startswith("genre:") or token.startswith("year:")]
    return " ".join(keep).strip()


def _extract_genres_from_query(safe_query: str):
    genres = []
    for token in safe_query.split():
        if token.startswith("genre:"):
            value = token.replace("genre:", "").strip().strip('()').strip('"').strip("'")
            if value and value not in genres:
                genres.append(value)
    return genres


def get_smart_candidates(search_query):
    safe_query = _sanitize_query(search_query)

    query_candidates = []
    if safe_query:
        query_candidates.append(str(safe_query))
        if "genre:hip-hop" in safe_query:
            query_candidates.append(str(safe_query.replace("genre:hip-hop", 'genre:"hip-hop"')))

    # Advanced-query fallbacks (still genre/year style)
    query_candidates.extend([
        "genre:pop",
        "genre:electronic",
        "genre:rock",
        "genre:indie",
        "genre:jazz",
    ])

    # Last-resort broad fallbacks
    query_candidates.extend([
        "pop",
        "electronic",
        "hip hop",
        "rock",
        "jazz",
        "track:love",
    ])

    ordered_unique = []
    for q in query_candidates:
        if q not in ordered_unique:
            ordered_unique.append(str(q))

    seen_ids = set()
    tracks = []
    debug_rows = []

    for query in ordered_unique:
        for market in ["US", None]:
            try:
                # NOTE: do not pass limit/offset to avoid account-specific "Invalid limit" parser issues.
                if market is not None:
                    results = sp.search(q=str(query), type='track', market=str(market))
                else:
                    results = sp.search(q=str(query), type='track')

                items = results.get('tracks', {}).get('items', [])
                debug_rows.append(
                    f"query={query} market={market or 'none'} count={len(items)}"
                )
                print(f"DEBUG: search '{query}' market={market or 'none'} -> {len(items)} tracks")
                for track in items:
                    track_id = (track or {}).get("id")
                    if track_id and track_id in seen_ids:
                        continue
                    if track_id:
                        seen_ids.add(track_id)
                    tracks.append(track)
                if len(tracks) >= 50:
                    return tracks[:50], debug_rows
            except Exception as e:
                debug_rows.append(
                    f"query={query} market={market or 'none'} error={e}"
                )
                print(f"DEBUG: search query failed '{query}' market={market or 'none'}: {e}")
                continue

    return tracks[:50], debug_rows
