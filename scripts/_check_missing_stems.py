"""Check which songs are missing stem separation."""
import json
import urllib.request

BASE = "http://localhost:8000"

# Login
data = json.dumps({"username": "qqq", "password": "12345678"}).encode()
req = urllib.request.Request(f"{BASE}/api/auth/login", data=data, headers={"Content-Type": "application/json"}, method="POST")
resp = json.loads(urllib.request.urlopen(req).read())
token = resp["data"]["access_token"]

# Get all songs
req = urllib.request.Request(f"{BASE}/api/library/songs", headers={"Authorization": f"Bearer {token}"})
result = json.loads(urllib.request.urlopen(req).read())
songs = result.get("data", result)
if isinstance(songs, dict):
    songs = songs.get("songs", songs.get("items", []))

total = len(songs)
with_stems = 0
without_stems = []
error_analysis = []

for s in songs:
    title = s.get("title", "?")
    artist = s.get("artist", "?")
    stems = s.get("stems")
    status = s.get("analysis_status", "?")
    
    if stems:
        with_stems += 1
    else:
        without_stems.append(f"  {title} - {artist} (status={status})")
    
    if status == "error":
        error_analysis.append(f"  {title} - {artist}")

print(f"Total songs: {total}")
print(f"With stems: {with_stems}")
print(f"Without stems: {len(without_stems)}")
if without_stems:
    print("\nSongs WITHOUT stems:")
    for s in without_stems:
        print(s)

if error_analysis:
    print(f"\nSongs with analysis ERROR ({len(error_analysis)}):")
    for s in error_analysis:
        print(s)
