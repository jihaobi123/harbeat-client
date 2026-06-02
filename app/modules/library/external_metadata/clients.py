"""Convenience functions for running external metadata clients."""
from __future__ import annotations

import asyncio

from app.modules.library.external_metadata.discogs_client import fetch_discogs_metadata
from app.modules.library.external_metadata.lastfm_client import fetch_lastfm_metadata
from app.modules.library.external_metadata.musicbrainz_client import fetch_musicbrainz_metadata
from app.modules.library.external_metadata.schemas import ExternalSourceResult


async def fetch_all_external_metadata(
    *,
    title: str,
    artist: str,
    timeout_sec: float = 8.0,
) -> dict[str, ExternalSourceResult]:
    tasks = {
        "musicbrainz": fetch_musicbrainz_metadata(title=title, artist=artist, timeout_sec=timeout_sec),
        "lastfm": fetch_lastfm_metadata(title=title, artist=artist, timeout_sec=timeout_sec),
        "discogs": fetch_discogs_metadata(title=title, artist=artist, timeout_sec=timeout_sec),
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    out: dict[str, ExternalSourceResult] = {}
    for source, result in zip(tasks.keys(), results):
        if isinstance(result, ExternalSourceResult):
            out[source] = result
        elif isinstance(result, Exception):
            out[source] = ExternalSourceResult.error_result(source, str(result))
        else:
            out[source] = ExternalSourceResult.error_result(source, "unexpected result")
    return out

