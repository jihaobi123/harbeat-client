"""Playlist URL parser — Python port of electron/playlistParser.ts.

Supports:
  - NetEase Cloud Music (music.163.com)
  - QQ Music (y.qq.com)
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx

_log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Mobile shares often look like:
#   分享歌单: 名字 https://music.163.com/m/playlist?id=7461440491&creatorId=...
#   https://y.music.163.com/m/playlist?id=...
#   https://music.163.com/playlist/7461440491/
#   163cn.tv/abc123  (短链, 需要展开)
_NETEASE_HOSTS = ("music.163.com", "y.music.163.com", "163cn.tv")


def detect_platform(text: str) -> tuple[str, str]:
    """Return (platform, playlist_id_or_url).

    For NetEase: ID is extracted directly (numeric).
    For QQ Music short links: full URL is returned and resolved later.
    """
    s = (text or "").strip()
    # NetEase — id=...
    m = re.search(r"music\.163\.com[^\s]*?[?&#]id=(\d+)", s)
    if m:
        return "netease", m.group(1)
    # NetEase — /playlist/<id>/ path style
    m = re.search(r"music\.163\.com[^\s]*?/playlist/(\d+)", s)
    if m:
        return "netease", m.group(1)
    # NetEase — 163cn.tv short link, return URL for redirect resolution
    m = re.search(r"https?://163cn\.tv/[A-Za-z0-9]+", s)
    if m:
        return "netease_short", m.group(0)

    m = re.search(r"y\.qq\.com/n/ryqq/playlist/(\d+)", s)
    if m:
        return "qqmusic", m.group(1)

    m = re.search(r"y\.qq\.com/[^\s]*[?&]id=(\d+)", s)
    if m:
        return "qqmusic", m.group(1)

    m = re.search(r"https?://[a-z0-9.]*y\.qq\.com/[^\s)\"'<>]+", s)
    if m:
        return "qqmusic", m.group(0)

    return "unknown", ""


async def parse_playlist_url(text: str) -> dict:
    """Parse a playlist URL and return {name, platform, tracks: [{title, artist, album, duration}]}."""
    platform, pid = detect_platform(text)
    if platform == "netease":
        return await _fetch_netease(pid)
    if platform == "netease_short":
        pid = await _resolve_netease_short(pid)
        return await _fetch_netease(pid)
    if platform == "qqmusic":
        return await _fetch_qqmusic(pid)
    raise ValueError("无法识别歌单链接，请粘贴网易云或QQ音乐歌单链接")


# ─── NetEase ────────────────────────────────────────────────

async def _resolve_netease_short(short_url: str) -> str:
    """Follow 163cn.tv short link and extract playlist id from final URL."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        try:
            resp = await client.get(short_url, headers={"User-Agent": _UA})
        except httpx.HTTPError as e:
            raise ValueError(f"网易云短链展开失败: {e.__class__.__name__}")
    final_url = str(resp.url)
    m = re.search(r"[?&#]id=(\d+)", final_url) or re.search(r"/playlist/(\d+)", final_url)
    if not m:
        raise ValueError(f"网易云短链未指向歌单: {final_url}")
    return m.group(1)


async def _fetch_netease(playlist_id: str) -> dict:
    api_url = f"https://music.163.com/api/v3/playlist/detail?id={playlist_id}&n=5000"
    headers = {
        "User-Agent": _UA,
        "Referer": "https://music.163.com/",
        "Cookie": "appver=2.9.7; os=pc;",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            resp = await client.get(api_url, headers=headers)
    except httpx.TimeoutException:
        raise ValueError("网易云 API 超时（20秒），请稍后重试")
    except httpx.HTTPError as e:
        raise ValueError(f"网易云 API 网络错误: {e.__class__.__name__}: {e}")

    if resp.status_code != 200:
        # Common cases: 403 (geo block / rate limit), 404 (deleted), 5xx (api down)
        body_preview = (resp.text or "")[:200]
        raise ValueError(
            f"网易云 API 返回 HTTP {resp.status_code}（id={playlist_id}）: {body_preview}"
        )
    try:
        data = resp.json()
    except json.JSONDecodeError:
        body_preview = (resp.text or "")[:200]
        raise ValueError(f"网易云 API 返回非 JSON 响应: {body_preview}")

    code = data.get("code")
    if code != 200 or not data.get("playlist"):
        # NetEase common error codes: 401 unauth, 404 not exist, -460 geo
        msg = data.get("message") or data.get("msg") or "未知错误"
        raise ValueError(f"网易云返回失败 code={code}（id={playlist_id}）: {msg}")

    playlist = data["playlist"]
    tracks = [
        {
            "title": t.get("name", ""),
            "artist": " / ".join(a.get("name", "") for a in t.get("ar", [])) or "未知",
            "album": (t.get("al") or {}).get("name", ""),
            "duration": round((t.get("dt", 0)) / 1000),
        }
        for t in (playlist.get("tracks") or [])
    ]

    # If tracks are empty but trackIds exist, fetch details
    if not tracks and playlist.get("trackIds"):
        ids = [t["id"] for t in playlist["trackIds"][:500]]
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://music.163.com/api/v3/song/detail",
                    data={"c": json.dumps([{"id": i} for i in ids])},
                    headers={"User-Agent": _UA, "Referer": "https://music.163.com/"},
                )
                detail = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            _log.warning("netease song/detail fallback failed: %s", e)
            detail = {"songs": []}
        for t in detail.get("songs", []):
            tracks.append({
                "title": t.get("name", ""),
                "artist": " / ".join(a.get("name", "") for a in t.get("ar", [])) or "未知",
                "album": (t.get("al") or {}).get("name", ""),
                "duration": round((t.get("dt", 0)) / 1000),
            })

    if not tracks:
        raise ValueError(
            f"网易云歌单 id={playlist_id} 解析成功但无歌曲（可能为私密歌单或被下架）"
        )

    return {"name": playlist.get("name", "未知歌单"), "platform": "netease", "tracks": tracks}


# ─── QQ Music ───────────────────────────────────────────────

async def _resolve_qq_id(input_val: str) -> str:
    if re.match(r"^\d+$", input_val):
        return input_val
    # Follow redirect for short links
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        resp = await client.get(input_val, headers={"User-Agent": _UA})
        m = re.search(r"id=(\d+)", str(resp.url))
        if m:
            return m.group(1)
        m = re.search(r"/playlist/(\d+)", str(resp.url))
        if m:
            return m.group(1)
    raise ValueError("无法解析QQ音乐歌单ID")


async def _fetch_qqmusic(input_val: str) -> dict:
    disstid = await _resolve_qq_id(input_val)
    api_url = "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"
    params = {
        "type": "1",
        "utf8": "1",
        "disstid": disstid,
        "format": "json",
        "inCharset": "utf8",
        "outCharset": "utf-8",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(api_url, params=params, headers={
            "User-Agent": _UA,
            "Referer": "https://y.qq.com/",
        })
        resp.raise_for_status()
        data = resp.json()

    cdlist = data.get("cdlist", [])
    if not cdlist:
        raise ValueError("获取QQ音乐歌单失败")

    cd = cdlist[0]
    tracks = [
        {
            "title": t.get("songname", ""),
            "artist": " / ".join(s.get("name", "") for s in t.get("singer", [])) or "未知",
            "album": t.get("albumname", ""),
            "duration": t.get("interval", 0),
        }
        for t in cd.get("songlist", [])
    ]
    return {"name": cd.get("dissname", "未知歌单"), "platform": "qqmusic", "tracks": tracks}
