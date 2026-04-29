"""Playlist URL parser — Python port of electron/playlistParser.ts.

Supports:
  - NetEase Cloud Music (music.163.com)
  - QQ Music (y.qq.com)
"""
from __future__ import annotations

import json
import re
from typing import Optional

import httpx

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def detect_platform(text: str) -> tuple[str, str]:
    """Return (platform, playlist_id).  platform is 'netease', 'qqmusic', or 'unknown'."""
    m = re.search(r"music\.163\.com.*[?&#]id=(\d+)", text)
    if m:
        return "netease", m.group(1)

    m = re.search(r"y\.qq\.com/n/ryqq/playlist/(\d+)", text)
    if m:
        return "qqmusic", m.group(1)

    m = re.search(r"y\.qq\.com/[^\s]*[?&]id=(\d+)", text)
    if m:
        return "qqmusic", m.group(1)

    m = re.search(r"https?://[a-z0-9.]*y\.qq\.com/[^\s)\"'<>]+", text)
    if m:
        return "qqmusic", m.group(0)

    return "unknown", ""


async def parse_playlist_url(text: str) -> dict:
    """Parse a playlist URL and return {name, platform, tracks: [{title, artist, album, duration}]}."""
    platform, pid = detect_platform(text)
    if platform == "netease":
        return await _fetch_netease(pid)
    if platform == "qqmusic":
        return await _fetch_qqmusic(pid)
    raise ValueError("无法识别歌单链接，请粘贴网易云或QQ音乐歌单链接")


# ─── NetEase ────────────────────────────────────────────────

async def _fetch_netease(playlist_id: str) -> dict:
    api_url = f"https://music.163.com/api/v3/playlist/detail?id={playlist_id}&n=5000"
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        resp = await client.get(api_url, headers={
            "User-Agent": _UA,
            "Referer": "https://music.163.com/",
            "Cookie": "appver=2.9.7; os=pc;",
        })
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != 200 or not data.get("playlist"):
        raise ValueError(data.get("message", "获取网易云歌单失败，歌单可能不存在或为私密歌单"))

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
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://music.163.com/api/v3/song/detail",
                data={"c": json.dumps([{"id": i} for i in ids])},
                headers={"User-Agent": _UA, "Referer": "https://music.163.com/"},
            )
            detail = resp.json()
        for t in detail.get("songs", []):
            tracks.append({
                "title": t.get("name", ""),
                "artist": " / ".join(a.get("name", "") for a in t.get("ar", [])) or "未知",
                "album": (t.get("al") or {}).get("name", ""),
                "duration": round((t.get("dt", 0)) / 1000),
            })

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
    api_url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    body = {
        "req_0": {
            "module": "srf_diss_info.DissInfoServer",
            "method": "CgiGetDiss",
            "param": {
                "disstid": int(disstid),
                "onlysonglist": 0,
                "song_begin": 0,
                "song_num": 500,
            },
        }
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(api_url, json=body, headers={
            "User-Agent": _UA,
            "Referer": "https://y.qq.com/",
        })
        resp.raise_for_status()
        data = resp.json()

    req0 = data.get("req_0", {})
    if req0.get("code") != 0:
        raise ValueError("获取QQ音乐歌单失败")

    diss_data = req0.get("data", {})
    dirinfo = diss_data.get("dirinfo", {})
    tracks = [
        {
            "title": t.get("title", ""),
            "artist": " / ".join(s.get("name", "") for s in t.get("singer", [])) or "未知",
            "album": (t.get("album") or {}).get("name", ""),
            "duration": t.get("interval", 0),
        }
        for t in diss_data.get("songlist", [])
    ]
    return {"name": dirinfo.get("title", "未知歌单"), "platform": "qqmusic", "tracks": tracks}
