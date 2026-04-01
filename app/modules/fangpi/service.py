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
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            r1 = await client.post(
                f"{_FANGPI_BASE}/api/s",
                data={"keyword": query.strip()},
                headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/"},
            )
            if r1.status_code >= 500:
                return []

            encoded = query.strip().replace(" ", "%20")
            resp = await client.get(
                f"{_FANGPI_BASE}/s/{encoded}",
                headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/"},
            )
            if resp.status_code >= 500:
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
    """Search songs — tries fangpi.net first, falls back to Kuwo."""
    results = await _fangpi_search(query)
    if results:
        return results
    logger.info("fangpi search returned 0 results, falling back to Kuwo for: %s", query)
    return await _kuwo_search(query)


async def smart_search_fangpi(title: str, artist: str) -> list[dict]:
    """Multi-strategy search to maximise match rate."""
    for q in [
        f"{title} {artist}".strip(),
        title.strip(),
        re.sub(r"[（(].*?[)）]", "", title).strip(),
    ]:
        if not q:
            continue
        results = await search_fangpi(q)
        if results:
            return results
    return []


async def _get_audio_url(music_id: str, source: str = "fangpi") -> str:
    """Resolve audio URL — tries the original source, falls back."""
    if source == "fangpi":
        try:
            return await _fangpi_get_audio_url(music_id)
        except Exception:
            logger.info("fangpi audio URL failed for %s, trying Kuwo", music_id)
            # fangpi IDs may differ from Kuwo IDs, so this may not work
            try:
                return await _kuwo_get_audio_url(music_id)
            except Exception:
                raise ValueError("所有音源均无法获取音频链接")
    else:
        return await _kuwo_get_audio_url(music_id)


# ───────────────── download ───────────────────────────────────


async def download_fangpi_song(
    music_id: str, title: str, artist: str, dest_dir: str,
    source: str = "fangpi",
) -> dict:
    """Download a song and save as MP3.

    Returns ``{file_path, file_size}``.  Raises on failure.
    """
    audio_url = await _get_audio_url(music_id, source)

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
