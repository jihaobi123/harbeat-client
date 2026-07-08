import os
import asyncio

import pytest

from app.modules.library.external_metadata.discogs_client import fetch_discogs_metadata
from app.modules.library.external_metadata.lastfm_client import fetch_lastfm_metadata
from app.modules.library.external_metadata.musicbrainz_client import fetch_musicbrainz_metadata


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_EXTERNAL_API_TESTS") != "1",
    reason="set RUN_LIVE_EXTERNAL_API_TESTS=1 to run live external API smoke tests",
)


TRACKS = [
    ("Zapp", "More Bounce To The Ounce"),
    ("James Brown", "Get Up Offa That Thing"),
    ("Afrika Bambaataa", "Planet Rock"),
]


def test_live_musicbrainz_smoke():
    artist, title = TRACKS[0]
    result = asyncio.run(fetch_musicbrainz_metadata(title=title, artist=artist, timeout_sec=10.0))
    print({"source": result.source, "status": result.status, "labels": result.normalized_labels()[:8], "mbid": result.mbid})
    assert result.status in {"hit", "miss", "error"}
    if result.status == "hit":
        assert result.mbid or result.labels


def test_live_lastfm_smoke():
    if not os.getenv("LASTFM_API_KEY"):
        pytest.skip("LASTFM_API_KEY is required for Last.fm live smoke test")
    hits = []
    for artist, title in TRACKS:
        result = asyncio.run(fetch_lastfm_metadata(title=title, artist=artist, timeout_sec=10.0))
        print({"source": result.source, "status": result.status, "labels": result.normalized_labels()[:8]})
        if result.status == "hit":
            hits.append(result)
    assert hits, "Last.fm should return tags for at least one test track"


def test_live_discogs_smoke():
    if not os.getenv("DISCOGS_USER_TOKEN"):
        pytest.skip("DISCOGS_USER_TOKEN is required for Discogs live smoke test")
    hits = []
    for artist, title in TRACKS:
        result = asyncio.run(fetch_discogs_metadata(title=title, artist=artist, timeout_sec=10.0))
        print({"source": result.source, "status": result.status, "labels": result.normalized_labels()[:8], "release_id": result.release_id})
        if result.status == "hit":
            hits.append(result)
    assert hits, "Discogs should return genre/style labels for at least one test track"
