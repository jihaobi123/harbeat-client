"""Test the fully fixed fangpi search logic."""
import asyncio
import re
import httpx

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_BASE = "https://www.fangpi.net"

def _clean_html(s):
    return s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", '"')

async def fixed_fangpi_search(query):
    """Simulates the fixed _fangpi_search."""
    # Strip problematic characters
    clean_query = re.sub(r'[./"\\]', ' ', query.strip())
    clean_query = re.sub(r'\s+', ' ', clean_query).strip()
    if not clean_query:
        return []
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
        r1 = await client.post(f"{_BASE}/api/s", data={"keyword": clean_query},
            headers={"User-Agent": _UA, "Referer": f"{_BASE}/"})
        
        search_path = None
        try:
            body = r1.json()
            if body.get("code") == 1 and body.get("data", {}).get("u"):
                search_path = body["data"]["u"]
        except:
            pass
        
        if search_path:
            search_url = f"{_BASE}{search_path}"
        else:
            from urllib.parse import quote
            search_url = f"{_BASE}/s/{quote(clean_query, safe='')}"
        
        resp = await client.get(search_url, headers={"User-Agent": _UA, "Referer": f"{_BASE}/"})
        if resp.status_code >= 400:
            return []
    
    results = []
    for m in re.finditer(r'href="/music/(\d+)"[^>]*?title="([^"]+)"', resp.text, re.DOTALL):
        full_title = _clean_html(m.group(2)).strip()
        parts = full_title.split(" - ", 1)
        results.append({
            "id": m.group(1),
            "title": parts[0].strip(),
            "artist": parts[1].strip() if len(parts) > 1 else "",
            "source": "fangpi",
        })
    return results

async def main():
    test_queries = [
        ('Nuthin\' But A "G" Thang', "Dr. Dre / Snoop Dogg"),
        ("Juicy", "The Notorious B.I.G."),
        ("Pieces Of A (Black) Man (Explicit)", "AZ"),
        ("Elevate", "Jigmastas"),
        ("My Block (Nitty Remix)", "2Pac"),
        ("Shook Ones Part II", "Mobb Deep"),
    ]
    
    found = 0
    for title, artist in test_queries:
        query = f"{title} {artist}"
        results = await fixed_fangpi_search(query)
        if not results:
            # Try title only
            results = await fixed_fangpi_search(title)
        
        if results:
            found += 1
            print(f"  OK: {title[:35]:35s} => {results[0]['title'][:30]} (id={results[0]['id']})")
        else:
            print(f"  MISS: {title[:35]:35s} => no results")
    
    print(f"\nFangpi match rate: {found}/{len(test_queries)}")

asyncio.run(main())
