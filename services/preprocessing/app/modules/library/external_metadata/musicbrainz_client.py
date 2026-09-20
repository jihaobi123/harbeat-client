"""MusicBrainz client for recording identity and tag metadata."""
from __future__ import annotations

from urllib.parse import quote

import httpx

from app.modules.library.external_metadata.schemas import ExternalSourceResult
from app.shared.config import get_settings


def _user_agent() -> str:
    settings = get_settings()
    app = settings.musicbrainz_app_name or "HarBeat"
    version = settings.musicbrainz_app_version or "1.0.0"
    contact = settings.musicbrainz_contact_email or "https://github.com/jihaobi123/harbeat-client"
    return f"{app}/{version} ({contact})"


async def fetch_musicbrainz_metadata(
    *,
    title: str,
    artist: str,
    timeout_sec: float = 8.0,
) -> ExternalSourceResult:
    if not title:
        return ExternalSourceResult.miss("musicbrainz")
    headers = {"User-Agent": _user_agent()}
    query = f'recording:"{title}"'
    if artist:
        query += f' AND artist:"{artist}"'
    try:
        async with httpx.AsyncClient(timeout=timeout_sec, headers=headers) as client:
            search = await client.get(
                "https://musicbrainz.org/ws/2/recording",
                params={"query": query, "fmt": "json", "limit": "3"},
            )
            search.raise_for_status()
            recordings = search.json().get("recordings") or []
            if not recordings:
                return ExternalSourceResult.miss("musicbrainz")
            best = recordings[0]
            mbid = best.get("id")
            labels: list[str] = []
            for tag in best.get("tags") or []:
                name = tag.get("name")
                if name:
                    labels.append(str(name))
            for genre in best.get("genres") or []:
                name = genre.get("name")
                if name:
                    labels.append(str(name))
            lookup_raw = {}
            if mbid:
                lookup = await client.get(
                    f"https://musicbrainz.org/ws/2/recording/{quote(mbid)}",
                    params={"inc": "artist-credits+releases+genres+tags", "fmt": "json"},
                )
                if lookup.status_code == 200:
                    lookup_raw = lookup.json()
                    for tag in lookup_raw.get("tags") or []:
                        name = tag.get("name")
                        if name:
                            labels.append(str(name))
                    for genre in lookup_raw.get("genres") or []:
                        name = genre.get("name")
                        if name:
                            labels.append(str(name))
            labels = list(dict.fromkeys(labels))
            score = float(best.get("score") or 0.0) / 100.0
            artists = best.get("artist-credit") or []
            matched_artist = ""
            if artists and isinstance(artists[0], dict):
                matched_artist = str((artists[0].get("artist") or {}).get("name") or "")
            return ExternalSourceResult(
                source="musicbrainz",
                status="hit" if labels or mbid else "miss",
                labels=labels,
                confidence=max(0.45, min(0.80, score or 0.55)),
                mbid=mbid,
                matched_title=best.get("title"),
                matched_artist=matched_artist,
                raw={
                    "recording_count": len(recordings),
                    "score": best.get("score"),
                    "lookup_has_tags": bool(lookup_raw.get("tags") or lookup_raw.get("genres")),
                },
            )
    except Exception as exc:
        return ExternalSourceResult.error_result("musicbrainz", str(exc))

