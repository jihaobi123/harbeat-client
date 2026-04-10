"""Test download on server - simulates what the frontend does."""
import httpx
import json

BASE = "http://localhost:8000/api"

# Step 1: batch-search to get a candidate (like frontend does)
print("=== Step 1: Batch Search ===")
r = httpx.post(f"{BASE}/fangpi/batch-search", json={
    "songs": [{"title": "Gold Digger", "artist": "Kanye West"}]
}, timeout=30)
d = r.json()
results = d.get("data", {}).get("results", [])
if not results or not results[0].get("candidates"):
    print("  No candidates found, cannot test download")
    exit(1)

candidate = results[0]["candidates"][0]
print(f"  Found: id={candidate['id']}, title={candidate['title']}, artist={candidate['artist']}, source={candidate['source']}")

# Step 2: Try download (needs auth - check if we get auth error or download error)
print("\n=== Step 2: Download (no auth - expect 401) ===")
r2 = httpx.post(f"{BASE}/fangpi/download", json={
    "music_id": candidate["id"],
    "title": candidate["title"],
    "artist": candidate["artist"],
    "source": candidate["source"],
}, timeout=60)
print(f"  status={r2.status_code}")
d2 = r2.json()
print(f"  response: {json.dumps(d2, ensure_ascii=False)[:300]}")

# Step 3: Test audio URL resolution directly (bypass API)
print("\n=== Step 3: Direct Kuwo audio URL test ===")
kuwo_id = candidate["id"]
r3 = httpx.get(
    f"https://antiserver.kuwo.cn/anti.s?type=convert_url3&rid={kuwo_id}&format=mp3&response=url",
    headers={"User-Agent": "okhttp/3.10.0"},
    timeout=15,
    follow_redirects=True,
)
print(f"  Kuwo antiserver status={r3.status_code}")
try:
    body = r3.json()
    url = body.get("url", "")
    print(f"  audio URL: {url[:80]}..." if url else f"  response: {r3.text[:200]}")
    
    if url:
        # Try downloading a small chunk
        r4 = httpx.get(url, headers={"User-Agent": "okhttp/3.10.0", "Range": "bytes=0-102400"}, timeout=30, follow_redirects=True)
        print(f"  Download test: status={r4.status_code}, size={len(r4.content)} bytes, content-type={r4.headers.get('content-type')}")
except Exception as e:
    print(f"  parse error: {e}, raw: {r3.text[:200]}")

print("\nDone!")
