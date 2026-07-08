"""Discogs client for release genre/style metadata."""
from __future__ import annotations

import httpx

from app.modules.library.external_metadata.schemas import ExternalSourceResult
from app.shared.config import get_settings


async def fetch_discogs_metadata(
    *,
    title: str,
    artist: str,
    timeout_sec: float = 8.0,
) -> ExternalSourceResult:
    settings = get_settings()
    token = settings.discogs_user_token.strip()
    if not token:
        return ExternalSourceResult.disabled("discogs")
    if not title:
        return ExternalSourceResult.miss("discogs")
    query = " ".join(v for v in (artist, title) if v).strip()
    headers = {
        "User-Agent": "HarBeat/1.0 +https://github.com/jihaobi123/harbeat-client",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_sec, headers=headers) as client:
            search = await client.get(
                "https://api.discogs.com/database/search",
                params={"q": query, "type": "release", "per_page": "3", "page": "1", "token": token},
            )
            search.raise_for_status()
            results = search.json().get("results") or []
            if not results:
                return ExternalSourceResult.miss("discogs")
            best = results[0]
            release_id = best.get("id")
            raw_labels: list[str] = []
            for key in ("genre", "style"):
                values = best.get(key) or []
                if isinstance(values, str):
                    raw_labels.append(values)
                else:
                    raw_labels.extend(str(v) for v in values if v)
            release_raw = {}
            if isinstance(release_id, int):
                detail = await client.get(
                    f"https://api.discogs.com/releases/{release_id}",
                    params={"token": token},
                )
                if detail.status_code == 200:
                    release_raw = detail.json()
                    for key in ("genres", "styles"):
                        values = release_raw.get(key) or []
                        if isinstance(values, str):
                            raw_labels.append(values)
                        else:
                            raw_labels.extend(str(v) for v in values if v)
            raw_labels = list(dict.fromkeys(raw_labels))
            if not raw_labels:
                return ExternalSourceResult.miss("discogs")
            confidence = 0.80 if release_raw else 0.68
            needs_review = bool(best.get("title")) and title.lower() not in str(best.get("title", "")).lower()
            return ExternalSourceResult(
                source="discogs",
                status="hit",
                labels=raw_labels,
                confidence=confidence,
                release_id=release_id if isinstance(release_id, int) else None,
                matched_title=best.get("title"),
                matched_artist=artist,
                needs_review=needs_review,
                raw={
                    "title": best.get("title"),
                    "year": release_raw.get("year") or best.get("year"),
                    "genres": release_raw.get("genres") or best.get("genre") or [],
                    "styles": release_raw.get("styles") or best.get("style") or [],
                },
            )
    except Exception as exc:
        return ExternalSourceResult.error_result("discogs", str(exc))

