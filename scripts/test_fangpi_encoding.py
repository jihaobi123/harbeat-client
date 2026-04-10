"""Test fangpi search with different queries - clean vs special chars."""
import asyncio
import re
import httpx

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_BASE = "https://www.fangpi.net"

async def test_fangpi(query):
    async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
        # POST first (init search)
        r1 = await client.post(f"{_BASE}/api/s", data={"keyword": query},
            headers={"User-Agent": _UA, "Referer": f"{_BASE}/"})
        print(f"  POST /api/s => {r1.status_code}, body={r1.text[:200]}")
        
        # GET search page (old method - just replacing spaces)
        encoded_old = query.replace(" ", "%20")
        r2 = await client.get(f"{_BASE}/s/{encoded_old}",
            headers={"User-Agent": _UA, "Referer": f"{_BASE}/"})
        matches_old = re.findall(r'href="/music/(\d+)"', r2.text)
        print(f"  GET /s/ (old encode) => {r2.status_code}, matches={len(matches_old)}")
        
        # GET search page (proper URL encoding)
        from urllib.parse import quote
        encoded_new = quote(query, safe='')
        r3 = await client.get(f"{_BASE}/s/{encoded_new}",
            headers={"User-Agent": _UA, "Referer": f"{_BASE}/"})
        matches_new = re.findall(r'href="/music/(\d+)"', r3.text)
        print(f"  GET /s/ (proper encode) => {r3.status_code}, matches={len(matches_new)}")

async def main():
    queries = [
        "If Trouble Was Money",           # clean - should work
        "Juicy The Notorious B.I.G.",     # has dots
        "Nuthin' But A G Thang",          # has apostrophe
        'Nuthin But A "G" Thang Dr. Dre / Snoop Dogg',  # has quotes and slash
        "Elevate Jigmastas",              # clean
        "Juicy",                          # simple
    ]
    for q in queries:
        print(f"\n--- {q[:50]} ---")
        await test_fangpi(q)

asyncio.run(main())
