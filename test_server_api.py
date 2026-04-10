"""Quick server-side API test for fangpi search + download."""
import httpx

BASE = "http://localhost:8000/api"

print("=== Test 1: Fangpi Search ===")
r = httpx.post(f"{BASE}/fangpi/search", json={"query": "Juicy"}, timeout=30)
d = r.json()
print(f"  code={d['code']}, results={len(d.get('data',{}).get('results',[]))}")
results = d.get("data", {}).get("results", [])
if results:
    first = results[0]
    print(f"  first: id={first.get('music_id')}, title={first.get('title')}, artist={first.get('artist')}")

print("\n=== Test 2: Fangpi Search with special chars ===")
r2 = httpx.post(f"{BASE}/fangpi/search", json={"query": "Juicy The Notorious B.I.G."}, timeout=30)
d2 = r2.json()
print(f"  code={d2['code']}, results={len(d2.get('data',{}).get('results',[]))}")
results2 = d2.get("data", {}).get("results", [])
if results2:
    first2 = results2[0]
    print(f"  first: id={first2.get('music_id')}, title={first2.get('title')}, artist={first2.get('artist')}")

print("\n=== Test 3: Batch Search (simulates playlist import) ===")
r3 = httpx.post(f"{BASE}/fangpi/batch-search", json={
    "songs": [
        {"title": "Juicy", "artist": "The Notorious B.I.G."},
        {"title": "Nuthin But A G Thang", "artist": "Dr. Dre"},
        {"title": "Gold Digger", "artist": "Kanye West"},
    ]
}, timeout=60)
d3 = r3.json()
print(f"  code={d3['code']}")
batch_results = d3.get("data", {}).get("results", [])
for item in batch_results:
    status = "FOUND" if item.get("results") else "NOT FOUND"
    print(f"  {item.get('title','?')} - {item.get('artist','?')}: {status} ({len(item.get('results',[]))} results)")

print("\nDone!")
