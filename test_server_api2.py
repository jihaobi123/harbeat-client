"""Quick server-side API test - correct field names."""
import httpx
import json

BASE = "http://localhost:8000/api"

print("=== Test 1: Fangpi Search ===")
r = httpx.post(f"{BASE}/fangpi/search", json={"query": "Juicy"}, timeout=30)
d = r.json()
print(f"  code={d.get('code')}")
songs = d.get("data", {}).get("songs", [])
print(f"  songs count: {len(songs)}")
for s in songs[:5]:
    print(f"    id={s.get('id')}, title={s.get('title')}, artist={s.get('artist')}, source={s.get('source')}")

print("\n=== Test 2: Search with special chars ===")
r2 = httpx.post(f"{BASE}/fangpi/search", json={"query": "Juicy The Notorious B.I.G."}, timeout=30)
d2 = r2.json()
songs2 = d2.get("data", {}).get("songs", [])
print(f"  code={d2.get('code')}, songs={len(songs2)}")
for s in songs2[:5]:
    print(f"    id={s.get('id')}, title={s.get('title')}, artist={s.get('artist')}, source={s.get('source')}")

print("\n=== Test 3: Batch Search ===")
r3 = httpx.post(f"{BASE}/fangpi/batch-search", json={
    "songs": [
        {"title": "Juicy", "artist": "The Notorious B.I.G."},
        {"title": "Nuthin But A G Thang", "artist": "Dr. Dre"},
        {"title": "Gold Digger", "artist": "Kanye West"},
    ]
}, timeout=60)
d3 = r3.json()
print(f"  code={d3.get('code')}")
print(f"  raw keys: {list(d3.get('data', {}).keys())}")
print(f"  data: {json.dumps(d3.get('data',{}), ensure_ascii=False)[:1000]}")

print("\nDone!")
