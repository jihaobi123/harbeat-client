import urllib.request, json

# Check API routes
r = urllib.request.urlopen("http://localhost/openapi.json")
d = json.loads(r.read())
paths = list(d.get("paths", {}).keys())
print(f"Total API routes: {len(paths)}")
for p in paths:
    print(f"  {p}")

# Check songs count
try:
    r2 = urllib.request.urlopen("http://localhost/api/library/songs?limit=3")
    data = json.loads(r2.read())
    print(f"\nSongs API response: code={data.get('code')}")
    songs = data.get("data", {})
    if isinstance(songs, list):
        print(f"Songs returned: {len(songs)}")
        for s in songs[:3]:
            print(f"  - {s.get('title','?')} | BPM: {s.get('bpm','?')}")
    elif isinstance(songs, dict) and "items" in songs:
        print(f"Songs returned: {len(songs['items'])}")
        for s in songs["items"][:3]:
            print(f"  - {s.get('title','?')} | BPM: {s.get('bpm','?')}")
    else:
        print(f"Songs data: {str(songs)[:200]}")
except Exception as e:
    print(f"Songs API error: {e}")

# Check users
try:
    r3 = urllib.request.urlopen("http://localhost/api/users/me")
    print(f"\nUsers API: {r3.status}")
except Exception as e:
    print(f"\nUsers API (expected 401): {e}")
