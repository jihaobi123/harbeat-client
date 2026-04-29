"""Test stem streaming - verify MP3 is served instead of WAV."""
import json
import urllib.request

BASE = "http://localhost:8000"

# Login
data = json.dumps({"username": "qqq", "password": "12345678"}).encode()
req = urllib.request.Request(f"{BASE}/api/auth/login", data=data, headers={"Content-Type": "application/json"}, method="POST")
resp = json.loads(urllib.request.urlopen(req).read())
token = resp["data"]["access_token"]
print(f"Token: {token[:20]}...")

# List user songs to find ones with stems
req = urllib.request.Request(f"{BASE}/api/library/songs", headers={"Authorization": f"Bearer {token}"})
songs = json.loads(urllib.request.urlopen(req).read())
song_list = songs.get("data", songs) if isinstance(songs, dict) else songs
if isinstance(song_list, dict):
    song_list = song_list.get("songs", song_list.get("items", []))

# Find songs with stems
tested = 0
for song in (song_list if isinstance(song_list, list) else []):
    sid = song.get("id", "")
    has_stems = song.get("stems") or song.get("has_stems")
    title = song.get("title", "?")
    if has_stems:
        print(f"\nSong {sid}: {title}")
        for stem in ["vocals"]:
            url = f"{BASE}/api/stream/{sid}/stem/{stem}?token={token}"
            try:
                req = urllib.request.Request(url, headers={"Range": "bytes=0-1023"})
                resp = urllib.request.urlopen(req)
                ct = resp.headers.get("Content-Type", "?")
                cl = resp.headers.get("Content-Length", "?")
                cr = resp.headers.get("Content-Range", "?")
                print(f"  stem={stem}: type={ct} range={cr} code={resp.status}")
            except Exception as e:
                print(f"  stem={stem}: ERROR {e}")
        tested += 1
        if tested >= 3:
            break

if tested == 0:
    print("No songs with stems found in API response")
    print(f"First song keys: {list(song_list[0].keys()) if song_list else 'empty'}")
