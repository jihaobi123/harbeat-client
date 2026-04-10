"""Debug: check raw responses from fangpi within the container."""
import httpx
import json

# Test 1: Direct fangpi.net connectivity
print("=== Network Test ===")
try:
    r = httpx.get("https://www.fangpi.net/", timeout=10)
    print(f"  fangpi.net: status={r.status_code}")
except Exception as e:
    print(f"  fangpi.net: FAILED - {e}")

try:
    r = httpx.get("https://search.kuwo.cn/r.s?ft=music&rn=1&all=test", timeout=10, follow_redirects=True)
    print(f"  kuwo search: status={r.status_code}, body[:100]={r.text[:100]}")
except Exception as e:
    print(f"  kuwo search: FAILED - {e}")

# Test 2: fangpi POST search API
print("\n=== Fangpi POST API ===")
try:
    r = httpx.post("https://www.fangpi.net/api/s", data={"w": "Juicy"}, timeout=15, follow_redirects=True)
    print(f"  status={r.status_code}")
    print(f"  body={r.text[:300]}")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 3: fangpi search page
print("\n=== Fangpi Search Page ===")
try:
    r = httpx.get("https://www.fangpi.net/s/Juicy", timeout=15, follow_redirects=True)
    print(f"  status={r.status_code}, len={len(r.text)}")
    # Check for music IDs
    import re
    ids = re.findall(r'/music/(\d+)', r.text)
    print(f"  music IDs found: {len(ids)}")
    if ids:
        print(f"  first 5: {ids[:5]}")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 4: Call our internal search function directly
print("\n=== Internal search_fangpi() ===")
try:
    from app.modules.fangpi.service import search_fangpi
    import asyncio
    results = asyncio.run(search_fangpi("Juicy"))
    print(f"  results count: {len(results)}")
    for r in results[:3]:
        print(f"  - id={r.get('music_id')}, title={r.get('title')}, artist={r.get('artist')}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")

# Test 5: smart_search
print("\n=== Internal smart_search_fangpi() ===")
try:
    from app.modules.fangpi.service import smart_search_fangpi
    import asyncio
    results = asyncio.run(smart_search_fangpi("Juicy", "The Notorious B.I.G."))
    print(f"  results count: {len(results)}")
    for r in results[:3]:
        print(f"  - id={r.get('music_id')}, title={r.get('title')}, artist={r.get('artist')}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")

print("\nDone!")
