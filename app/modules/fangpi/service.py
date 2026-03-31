"""Fangpi.net search and download service — Python port of electron/fangpiService.ts"""
from __future__ import annotations

import os
import re
import json
import urllib.parse

import httpx

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def search_fangpi(query: str) -> list[dict]:
    """Search songs on fangpi.net by keyword. Returns list of {id, title, artist, url}."""
    if not query.strip():
        return []
    # Use httpx params to avoid encoding issues; fangpi accepts path segments
    search_url = f"https://www.fangpi.net/s/{urllib.parse.quote(query.strip())}"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            resp = await client.get(search_url, headers=_HEADERS)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError:
        # Try alternative approach: use the search form endpoint
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
                resp = await client.get(
                    "https://www.fangpi.net/s",
                    params={"keyword": query.strip()},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                html = resp.text
        except Exception:
            return []
    except Exception:
        return []

    return _parse_search_results(html)


def _parse_search_results(html: str) -> list[dict]:
    start = html.find("搜索结果")
    if start < 0:
        return []
    end = len(html)
    for marker in ("热门推荐", "相关专题", "大家都在搜"):
        idx = html.find(marker, start)
        if idx > 0:
            end = min(end, idx)
    section = html[start:end]

    results: list[dict] = []
    seen: set[str] = set()
    # The href and title attributes may be on different lines with other tags in between
    pattern = re.compile(
        r"""<a[^>]*?href=["']/music/(\d+)["'].*?title=["']([^"']+?)["']""",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(section):
        mid = m.group(1)
        raw_title = m.group(2).strip()
        if mid in seen or not raw_title:
            continue
        seen.add(mid)
        # Title format: "song_name - artist_name"
        parts = raw_title.split(" - ", 1)
        title = _decode_html(parts[0].strip())
        artist = _decode_html(parts[1].strip()) if len(parts) > 1 else "未知"
        results.append({"id": mid, "title": title, "artist": artist, "url": f"https://www.fangpi.net/music/{mid}"})
    return results


def _decode_html(s: str) -> str:
    return (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#039;", "'")
    )


async def smart_search_fangpi(title: str, artist: str) -> list[dict]:
    """Search fangpi with multiple strategies to maximize match rate.

    Tries: 1) "title artist"  2) title only  3) artist only (if title has no results)
    """
    # Strategy 1: title + artist combined
    query1 = f"{title} {artist}".strip()
    results = await search_fangpi(query1)
    if results:
        return results

    # Strategy 2: title only
    results = await search_fangpi(title.strip())
    if results:
        return results

    # Strategy 3: simplified title (remove parenthetical content)
    simple_title = re.sub(r"[（(].*?[)）]", "", title).strip()
    if simple_title and simple_title != title.strip():
        results = await search_fangpi(simple_title)
        if results:
            return results

    return []


async def get_fangpi_audio_url(music_id: str) -> str:
    """Get the direct CDN audio URL for a fangpi.net music page."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        resp = await client.get(f"https://www.fangpi.net/music/{music_id}", headers=_HEADERS)
        resp.raise_for_status()
        page = resp.text

    m = re.search(r"window\.appData\s*=\s*JSON\.parse\('(.+?)'\)", page)
    if not m:
        raise ValueError("Cannot find appData on music page")

    raw = m.group(1)
    # Decode double-escaped unicode
    PLACEHOLDER = "\x00UESC"
    decoded = re.sub(r"\\\\u([0-9a-fA-F]{4})", PLACEHOLDER + r"\1", raw)
    decoded = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda x: chr(int(x.group(1), 16)),
        decoded,
    )
    decoded = decoded.replace(PLACEHOLDER, "\\u")
    decoded = decoded.replace("\\/", "/")

    app_data = json.loads(decoded)
    play_id = app_data.get("play_id")
    if not play_id:
        raise ValueError("No play_id in appData")

    # POST to /api/play-url
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://www.fangpi.net/api/play-url",
            data=f"id={urllib.parse.quote(str(play_id))}",
            headers={
                **_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.fangpi.net/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        resp.raise_for_status()
        body = resp.json()

    if body.get("code") == 1 and body.get("data", {}).get("url"):
        return body["data"]["url"]
    raise ValueError(body.get("msg", "API returned error"))


async def download_fangpi_song(music_id: str, title: str, artist: str, dest_dir: str) -> dict:
    """Download a song from fangpi.net. Returns {file_path, file_size}."""
    audio_url = await get_fangpi_audio_url(music_id)
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", f"{title} - {artist}")[:200]
    file_path = os.path.join(dest_dir, f"{safe_name}.mp3")

    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        resp = await client.get(audio_url, headers={"User-Agent": _HEADERS["User-Agent"]})
        resp.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(resp.content)

    return {"file_path": file_path, "file_size": os.path.getsize(file_path)}
