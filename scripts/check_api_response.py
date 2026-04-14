"""Check what the playlist API returns - does it include BPM/duration?"""
import httpx, json, sys
sys.path.insert(0, "/app")

# Check playlist API response
r = httpx.get("http://localhost:8000/api/playlists/1", timeout=10)
data = r.json()
print(f"Playlist API status: {data.get('code')}")

playlist_data = data.get("data", {})
songs = playlist_data.get("songs", [])
print(f"Songs in playlist: {len(songs)}")

if songs:
    print(f"\nFirst song keys: {list(songs[0].keys())}")
    for s in songs[:3]:
        print(f"  title={s.get('title')}, bpm={s.get('bpm')}, duration={s.get('duration')}, key={s.get('key')}, format={s.get('format')}")

# Also check library API
print("\n--- Library API ---")
r2 = httpx.get("http://localhost:8000/api/library/songs", timeout=10)
data2 = r2.json()
lib_songs = data2.get("data", {}).get("songs", data2.get("data", []))
if isinstance(lib_songs, list) and lib_songs:
    print(f"Library songs: {len(lib_songs)}")
    print(f"First song keys: {list(lib_songs[0].keys())}")
    for s in lib_songs[:3]:
        print(f"  title={s.get('title')}, bpm={s.get('bpm')}, duration={s.get('duration')}, key={s.get('key')}")
else:
    print(f"Library response: {json.dumps(data2, ensure_ascii=False)[:500]}")
