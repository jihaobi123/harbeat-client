"""Test batch search: check what sources are returned."""
import asyncio
import re
import httpx

_UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_UA_MOBILE = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/116.0 Mobile Safari/537.36"
_FANGPI_BASE = "https://www.fangpi.net"

def _clean_html(s):
    return s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", '"')

async def _fangpi_search(query):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            r1 = await client.post(f"{_FANGPI_BASE}/api/s", data={"keyword": query}, headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/"})
            if r1.status_code >= 400:
                print(f"  [fangpi] POST /api/s => {r1.status_code}")
            encoded = query.replace(" ", "%20")
            resp = await client.get(f"{_FANGPI_BASE}/s/{encoded}", headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/"})
            if resp.status_code >= 400:
                print(f"  [fangpi] GET /s/ => {resp.status_code}")
                return []
            results = []
            for m in re.finditer(r'href="/music/(\d+)"[^>]*?title="([^"]+)"', resp.text):
                results.append({"id": m.group(1), "title": _clean_html(m.group(2)).split(" - ")[0], "source": "fangpi"})
            return results
    except Exception as e:
        print(f"  [fangpi] error: {e}")
        return []

async def _kuwo_search(query):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            resp = await client.get("https://search.kuwo.cn/r.s",
                params={"ft": "music", "rformat": "json", "encoding": "utf8", "rn": "20", "pn": "0", "all": query},
                headers={"User-Agent": _UA_MOBILE, "Referer": "https://m.kuwo.cn/"})
            text = resp.text
        ids = re.findall(r"['\"]MUSICRID['\"]:\s*['\"]MUSIC_(\d+)['\"]", text)
        names = re.findall(r"['\"]NAME['\"]\s*:\s*['\"]([^'\"]*)['\"]", text)
        return [{"id": ids[i], "title": _clean_html(names[i]) if i < len(names) else "?", "source": "kuwo"} for i in range(len(ids))]
    except Exception as e:
        print(f"  [kuwo] error: {e}")
        return []

async def main():
    songs = [
        ("Nuthin' But A \"G\" Thang", "Dr. Dre / Snoop Dogg"),
        ("Pieces Of A (Black) Man (Explicit)", "AZ"),
        ("Elevate", "Jigmastas"),
        ("My Block (Nitty Remix)", "2Pac"),
        ("Juicy", "The Notorious B.I.G."),
    ]
    for title, artist in songs:
        query = f"{title} {artist}"
        print(f"\nSearching: {query[:60]}")
        fangpi = await _fangpi_search(query)
        kuwo = await _kuwo_search(query)
        
        # Combine like the real code does
        seen = set()
        combined = []
        for s in fangpi + kuwo:
            key = s["title"].lower().strip()
            if key not in seen:
                seen.add(key)
                combined.append(s)
        
        if combined:
            best = combined[0]
            print(f"  Best match: id={best['id']}, title={best['title'][:40]}, SOURCE={best['source']}")
        else:
            print(f"  NO RESULTS")

asyncio.run(main())
