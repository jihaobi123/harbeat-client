"""Music search and download service.

Primary source: fangpi.net (when available).
Fallback: Kuwo mobile API (search.kuwo.cn + antiserver.kuwo.cn).

Both sources ultimately serve audio from Kuwo CDN.
"""
from __future__ import annotations

import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

# ───────────────── constants ──────────────────────────────────

_UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_UA_MOBILE = (
    "Mozilla/5.0 (Linux; Android 13) "
    "AppleWebKit/537.36 Chrome/116.0 Mobile Safari/537.36"
)
_UA_DOWNLOAD = "okhttp/3.10.0"
_FANGPI_BASE = "https://www.fangpi.net"
_MIN_REAL_FILE_SIZE = 200_000  # 200 KB — anything smaller is a placeholder


def _clean_html(s: str) -> str:
    return (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&apos;", "'")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("\\u0026", "&")
        .replace("\\\\u0026", "&")
    )


# ╔═══════════════════════════════════════════════════════════╗
# ║  FANGPI.NET  (primary)                                   ║
# ╚═══════════════════════════════════════════════════════════╝


async def _fangpi_search(query: str) -> list[dict]:
    """Search via fangpi.net.  Returns [] on any failure (including 520)."""
    if not query.strip():
        return []
    # Strip characters that cause fangpi 404: dots, slashes, quotes
    clean_query = re.sub(r'[./"\\]', ' ', query.strip())
    clean_query = re.sub(r'\s+', ' ', clean_query).strip()
    if not clean_query:
        return []
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            r1 = await client.post(
                f"{_FANGPI_BASE}/api/s",
                data={"keyword": clean_query},
                headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/"},
            )
            if r1.status_code >= 500:
                return []

            # Use the URL returned by fangpi's POST API when available
            search_path = None
            try:
                body = r1.json()
                if body.get("code") == 1 and body.get("data", {}).get("u"):
                    search_path = body["data"]["u"]
            except Exception:
                pass

            if search_path:
                search_url = f"{_FANGPI_BASE}{search_path}"
            else:
                from urllib.parse import quote
                search_url = f"{_FANGPI_BASE}/s/{quote(clean_query, safe='')}"

            resp = await client.get(
                search_url,
                headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/"},
            )
            if resp.status_code >= 400:
                return []
            html = resp.text
    except Exception:
        return []

    results: list[dict] = []
    seen_ids: set[str] = set()
    for match in re.finditer(r'href="/music/(\d+)"[^>]*?title="([^"]+)"', html, re.DOTALL):
        mid = match.group(1)
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        full_title = _clean_html(match.group(2)).strip()
        parts = full_title.split(" - ", 1)
        title = parts[0].strip()
        artist = parts[1].strip() if len(parts) > 1 else ""
        results.append({
            "id": str(mid),
            "title": title,
            "artist": artist,
            "url": f"{_FANGPI_BASE}/music/{mid}",
            "duration": 0,
            "free": True,
            "source": "fangpi",
        })
    return results


async def _fangpi_get_audio_url(music_id: str) -> str:
    """Resolve a fangpi music_id → CDN audio URL.  Raises on failure."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
        resp = await client.get(
            f"{_FANGPI_BASE}/music/{music_id}",
            headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/"},
        )
        if resp.status_code >= 500:
            raise ValueError("fangpi 不可用")
        m = re.search(r"window\.appData\s*=\s*JSON\.parse\('(.+?)'\)", resp.text)
        if not m:
            raise ValueError("无法获取歌曲信息")
        raw = m.group(1).encode("utf-8").decode("unicode_escape")
        data = json.loads(raw)
        play_id = data.get("play_id", "")
        if not play_id:
            raise ValueError("play_id 为空")

        r2 = await client.post(
            f"{_FANGPI_BASE}/api/play-url",
            data={"id": play_id},
            headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/music/{music_id}"},
        )
        body = r2.json()
        if body.get("code") == 1 and body.get("data", {}).get("url"):
            return body["data"]["url"]

    raise ValueError("无法获取音频链接")


# ╔═══════════════════════════════════════════════════════════╗
# ║  KUWO  (fallback)                                        ║
# ╚═══════════════════════════════════════════════════════════╝


async def _kuwo_search(query: str) -> list[dict]:
    """Search via Kuwo mobile API.  Returns [] on failure."""
    if not query.strip():
        return []
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            resp = await client.get(
                "https://search.kuwo.cn/r.s",
                params={
                    "ft": "music", "rformat": "json", "encoding": "utf8",
                    "rn": "20", "pn": "0", "all": query.strip(),
                },
                headers={"User-Agent": _UA_MOBILE, "Referer": "https://m.kuwo.cn/"},
            )
            text = resp.text
    except Exception:
        return []

    ids = re.findall(r"['\"]MUSICRID['\"]:\s*['\"]MUSIC_(\d+)['\"]", text)
    names = re.findall(r"['\"]NAME['\"]\s*:\s*['\"]([^'\"]*)['\"]", text)
    artists = re.findall(r"['\"]ARTIST['\"]\s*:\s*['\"]([^'\"]*)['\"]", text)
    durations = re.findall(r"['\"]DURATION['\"]\s*:\s*['\"](\d+)['\"]", text)

    results: list[dict] = []
    for i, mid in enumerate(ids):
        title = _clean_html(names[i]) if i < len(names) else ""
        artist = _clean_html(artists[i]) if i < len(artists) else ""
        dur = int(durations[i]) if i < len(durations) else 0
        results.append({
            "id": str(mid),
            "title": title,
            "artist": artist,
            "url": f"https://www.kuwo.cn/play_detail/{mid}",
            "duration": dur,
            "free": True,
            "source": "kuwo",
        })
    return results


async def _kuwo_get_audio_url(music_id: str) -> str:
    """Get audio URL from Kuwo antiserver.  Raises on failure."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
        resp = await client.get(
            f"https://antiserver.kuwo.cn/anti.s"
            f"?type=convert_url3&rid={music_id}&format=mp3&response=url",
            headers={"User-Agent": _UA_DOWNLOAD},
        )
        # New format: JSON response {"code":200,"msg":"success","url":"..."}
        try:
            body = resp.json()
            url = body.get("url", "")
            if url:
                return url
        except Exception:
            # Old format: plain text URL
            url = resp.text.strip()
            if url.startswith("http"):
                return url

    raise ValueError("Kuwo: 无法获取音频链接")


# ╔═══════════════════════════════════════════════════════════╗
# ║  PUBLIC API  (fangpi first, Kuwo fallback)                ║
# ╚═══════════════════════════════════════════════════════════╝


async def search_fangpi(query: str) -> list[dict]:
    """Search songs — combines fangpi.net + Kuwo results for better coverage."""
    import asyncio

    fangpi_results, kuwo_results = await asyncio.gather(
        _fangpi_search(query),
        _kuwo_search(query),
        return_exceptions=True,
    )
    if isinstance(fangpi_results, Exception):
        fangpi_results = []
    if isinstance(kuwo_results, Exception):
        kuwo_results = []

    # Deduplicate by normalized title+artist
    seen: set[str] = set()
    combined: list[dict] = []
    for song in list(fangpi_results) + list(kuwo_results):
        key = (song["title"].lower().strip() + "|" + song["artist"].lower().strip())
        if key in seen:
            continue
        seen.add(key)
        combined.append(song)

    return combined


def _normalize_title(t: str) -> str:
    """Lowercase, strip parenthesized suffixes, remove punctuation."""
    t = t.lower().strip()
    t = re.sub(r"[（(].*?[)）]", "", t)
    t = re.sub(r"[^\w\s]", "", t)
    return t.strip()


def _title_matches(candidate_title: str, target_title: str) -> bool:
    """Check if candidate is a reasonable match for target."""
    a = _normalize_title(candidate_title)
    b = _normalize_title(target_title)
    if not a or not b:
        return False
    # Exact match or one contains the other
    if a == b or a in b or b in a:
        return True
    # Word overlap: at least 50% of target words appear in candidate
    a_words = set(a.split())
    b_words = set(b.split())
    if not b_words:
        return False
    overlap = len(a_words & b_words) / len(b_words)
    return overlap >= 0.5


async def smart_search_fangpi(title: str, artist: str) -> list[dict]:
    """Multi-strategy search to maximise match rate.

    Filters results to only include songs whose title reasonably matches
    the target, preventing completely wrong downloads.
    """
    for q in [
        f"{title} {artist}".strip(),
        title.strip(),
        re.sub(r"[（(].*?[)）]", "", title).strip(),
    ]:
        if not q:
            continue
        results = await search_fangpi(q)
        # Filter to only title-matching results
        matched = [r for r in results if _title_matches(r["title"], title)]
        if matched:
            return matched
    return []


async def _get_audio_url(music_id: str, source: str = "fangpi",
                         title: str = "", artist: str = "") -> str:
    """Resolve audio URL — tries the original source, falls back.

    When fangpi fails, re-searches Kuwo by title+artist to get the correct
    Kuwo ID (fangpi IDs ≠ Kuwo IDs), then downloads from Kuwo.
    """
    errors: list[str] = []

    if source == "fangpi":
        try:
            return await _fangpi_get_audio_url(music_id)
        except Exception as e:
            errors.append(f"fangpi: {e}")
            logger.info("fangpi audio URL failed for %s: %s", music_id, e)

    # Try Kuwo with the original ID (works when source is kuwo)
    if source == "kuwo":
        try:
            return await _kuwo_get_audio_url(music_id)
        except Exception as e:
            errors.append(f"kuwo(original id): {e}")
            logger.info("kuwo audio URL failed for %s: %s", music_id, e)

    # Fallback: search Kuwo by title+artist to find the correct Kuwo ID
    if title:
        query = f"{title} {artist}".strip() if artist else title
        logger.info("Fallback: searching Kuwo for '%s'", query)
        try:
            kuwo_results = await _kuwo_search(query)
            # Find best match by normalized title
            title_lower = title.lower().strip()
            for candidate in kuwo_results:
                if candidate["title"].lower().strip() == title_lower:
                    try:
                        url = await _kuwo_get_audio_url(candidate["id"])
                        logger.info("Kuwo fallback succeeded for '%s' with id %s", title, candidate["id"])
                        return url
                    except Exception as e:
                        errors.append(f"kuwo(matched id {candidate['id']}): {e}")
            # If no exact match, try the first result
            if kuwo_results:
                try:
                    url = await _kuwo_get_audio_url(kuwo_results[0]["id"])
                    logger.info("Kuwo fallback (first result) succeeded for '%s' with id %s", title, kuwo_results[0]["id"])
                    return url
                except Exception as e:
                    errors.append(f"kuwo(first result {kuwo_results[0]['id']}): {e}")
        except Exception as e:
            errors.append(f"kuwo search: {e}")

    raise ValueError(f"所有音源均无法获取音频链接: {'; '.join(errors)}")


# ───────────────── download ───────────────────────────────────


async def download_fangpi_song(
    music_id: str, title: str, artist: str, dest_dir: str,
    source: str = "fangpi",
) -> dict:
    """Download a song and save as MP3.

    Returns ``{file_path, file_size}``.  Raises on failure.
    """
    audio_url = await _get_audio_url(music_id, source, title=title, artist=artist)

    safe_name = re.sub(r'[<>:"/\\|?*]', "_", f"{title} - {artist}")[:200]
    file_path = os.path.join(dest_dir, f"{safe_name}.mp3")

    # Download with retry (CDN connections can drop)
    content = b""
    last_err = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
                resp = await client.get(audio_url, headers={"User-Agent": _UA_DOWNLOAD})
                resp.raise_for_status()
                content = resp.content
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                import asyncio
                await asyncio.sleep(1)
    else:
        raise ValueError(f"下载失败(重试3次): {last_err}")

    if len(content) < _MIN_REAL_FILE_SIZE:
        raise ValueError(
            f"下载的文件过小 ({len(content)} bytes)，该歌曲可能需要VIP才能下载完整版"
        )

    with open(file_path, "wb") as f:
        f.write(content)

    return {"file_path": file_path, "file_size": os.path.getsize(file_path)}
