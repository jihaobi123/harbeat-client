"""Minimal test: playlist URL parsing + audio URL resolution (no app imports)."""
import asyncio
import json
import re
import httpx

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def test_netease():
    print("=== NetEase ===")
    playlist_id = "25672837"
    api_url = f"https://music.163.com/api/v3/playlist/detail?id={playlist_id}&n=5000"
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        resp = await client.get(api_url, headers={
            "User-Agent": _UA,
            "Referer": "https://music.163.com/",
            "Cookie": "appver=2.9.7; os=pc;",
        })
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Code: {data.get('code')}, Message: {data.get('message', 'N/A')}")
        playlist = data.get("playlist", {})
        tracks = playlist.get("tracks", [])
        track_ids = playlist.get("trackIds", [])
        print(f"Name: {playlist.get('name')}, Tracks: {len(tracks)}, TrackIds: {len(track_ids)}")
        if tracks:
            for t in tracks[:3]:
                artists = " / ".join(a.get("name", "") for a in t.get("ar", []))
                print(f"  {t.get('name')} - {artists}")
        elif track_ids:
            print(f"  (tracks empty but {len(track_ids)} trackIds found - needs second fetch)")

async def test_qq():
    print("\n=== QQ Music ===")
    short_url = "https://c6.y.qq.com/base/fcgi-bin/u?__=BLW6bHdztqbb"
    print(f"Resolving short URL: {short_url}")
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        try:
            resp = await client.get(short_url, headers={"User-Agent": _UA})
            final_url = str(resp.url)
            print(f"Final URL: {final_url}")
            m = re.search(r"id=(\d+)", final_url)
            if m:
                print(f"Extracted id: {m.group(1)}")
            m2 = re.search(r"/playlist/(\d+)", final_url)
            if m2:
                print(f"Extracted playlist id: {m2.group(1)}")
            if not m and not m2:
                print(f"Could not extract playlist ID from final URL")
                print(f"Response body (first 500 chars): {resp.text[:500]}")
        except Exception as e:
            print(f"Error: {e}")

async def test_fangpi_search():
    print("\n=== Fangpi/Kuwo Search ===")
    query = "Nuthin But A G Thang Dr. Dre"
    # Kuwo search
    async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
        resp = await client.get(
            "https://search.kuwo.cn/r.s",
            params={"ft": "music", "rformat": "json", "encoding": "utf8", "rn": "5", "pn": "0", "all": query},
            headers={
                "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/116.0 Mobile Safari/537.36",
                "Referer": "https://m.kuwo.cn/",
            },
        )
        print(f"Kuwo search status: {resp.status_code}")
        text = resp.text
        ids = re.findall(r"['\"]MUSICRID['\"]:\s*['\"]MUSIC_(\d+)['\"]", text)
        names = re.findall(r"['\"]NAME['\"]\s*:\s*['\"]([^'\"]*)['\"]", text)
        print(f"Found {len(ids)} results")
        for i, mid in enumerate(ids[:3]):
            name = names[i] if i < len(names) else "?"
            print(f"  id={mid}, name={name}")
    
    # Try to get audio URL from kuwo
    if ids:
        mid = ids[0]
        print(f"\nTrying Kuwo audio URL for id={mid}...")
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            resp = await client.get(
                f"https://antiserver.kuwo.cn/anti.s?type=convert_url3&rid={mid}&format=mp3&response=url",
                headers={"User-Agent": "okhttp/3.10.0"},
            )
            print(f"Status: {resp.status_code}")
            print(f"Response (first 200 chars): {resp.text[:200]}")

    # Fangpi search
    print("\n--- Fangpi.net search ---")
    async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
        try:
            r1 = await client.post(
                "https://www.fangpi.net/api/s",
                data={"keyword": query},
                headers={"User-Agent": _UA, "Referer": "https://www.fangpi.net/"},
            )
            print(f"Fangpi POST status: {r1.status_code}")
            resp = await client.get(
                f"https://www.fangpi.net/s/{query.replace(' ', '%20')}",
                headers={"User-Agent": _UA, "Referer": "https://www.fangpi.net/"},
            )
            print(f"Fangpi GET status: {resp.status_code}")
            matches = re.findall(r'href="/music/(\d+)"[^>]*?title="([^"]+)"', resp.text)
            print(f"Found {len(matches)} matches")
            for mid, title in matches[:3]:
                print(f"  id={mid}, title={title}")
        except Exception as e:
            print(f"Fangpi error: {e}")

async def main():
    await test_netease()
    await test_qq()
    await test_fangpi_search()

asyncio.run(main())
