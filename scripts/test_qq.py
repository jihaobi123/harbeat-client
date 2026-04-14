"""Test QQ Music full playlist fetch."""
import asyncio
import re
import httpx

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def main():
    # Step 1: resolve short URL to playlist ID
    short_url = "https://c6.y.qq.com/base/fcgi-bin/u?__=BLW6bHdztqbb"
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        resp = await client.get(short_url, headers={"User-Agent": _UA})
        final_url = str(resp.url)
        print(f"Final URL: {final_url}")
        m = re.search(r"/playlist/(\d+)", final_url)
        disstid = m.group(1) if m else None
        print(f"Playlist ID: {disstid}")
    
    if not disstid:
        print("FAILED to resolve playlist ID")
        return
    
    # Step 2: fetch playlist info (old API)
    print("\n--- Old API (fcg_ucc_getcdinfo) ---")
    api_url = "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"
    params = {
        "type": "1", "utf8": "1", "disstid": disstid,
        "format": "json", "inCharset": "utf8", "outCharset": "utf-8",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(api_url, params=params, headers={
            "User-Agent": _UA, "Referer": "https://y.qq.com/",
        })
        print(f"Status: {resp.status_code}")
        data = resp.json()
        cdlist = data.get("cdlist", [])
        print(f"cdlist count: {len(cdlist)}")
        if cdlist:
            cd = cdlist[0]
            songlist = cd.get("songlist", [])
            print(f"Name: {cd.get('dissname')}, Songs: {len(songlist)}")
            for s in songlist[:3]:
                print(f"  {s.get('songname')} - {', '.join(si.get('name','') for si in s.get('singer',[]))}")
        else:
            print(f"Response keys: {list(data.keys())}")
            print(f"Response (first 500): {resp.text[:500]}")
    
    # Step 3: try new u.y.qq.com API as alternative
    print("\n--- New API (u.y.qq.com) ---")
    new_api = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    req_body = {
        "req_0": {
            "module": "srf_diss_info.DissInfoServer",
            "method": "CgiGetDiss",
            "param": {
                "disstid": int(disstid),
                "onlysonglist": 0,
                "song_begin": 0,
                "song_num": 100,
            }
        }
    }
    import json
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(new_api, json=req_body, headers={
            "User-Agent": _UA, "Referer": "https://y.qq.com/",
        })
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Code: {data.get('code')}")
        req0 = data.get("req_0", {})
        print(f"req_0 code: {req0.get('code')}")
        diss_data = req0.get("data", {})
        dirinfo = diss_data.get("dirinfo", {})
        songlist = diss_data.get("songlist", [])
        print(f"Name: {dirinfo.get('title')}, Songs: {len(songlist)}")
        for s in songlist[:3]:
            title = s.get("title", "")
            singers = " / ".join(si.get("name", "") for si in s.get("singer", []))
            print(f"  {title} - {singers}")

asyncio.run(main())
