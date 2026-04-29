"""Test the multi-engine beat analysis API on the cloud server."""
import json
import requests
import time

BASE = "http://localhost:8000"

# 1. Login
print("=" * 60)
print("1. LOGIN")
resp = requests.post(f"{BASE}/api/auth/login", json={"username": "qqq", "password": "12345678"})
print(f"   Status: {resp.status_code}")
data = resp.json()
token = data.get("data", {}).get("access_token", "")
print(f"   Token: {token[:30]}...")
headers = {"Authorization": f"Bearer {token}"}

# 2. List library songs
print("\n" + "=" * 60)
print("2. LIST LIBRARY SONGS")
resp = requests.get(f"{BASE}/api/library/songs", headers=headers)
print(f"   Status: {resp.status_code}")
songs = resp.json().get("data", {}).get("songs", [])
print(f"   Found {len(songs)} songs")

if not songs:
    print("   No songs found for this user. Skipping analysis test.")
    exit(0)

# Pick first song
song = songs[0]
song_id = song["id"]
print(f"   First song: {song['title']} - {song['artist']} (id={song_id})")
print(f"   Current BPM: {song.get('bpm')}")
print(f"   Current beat_confidence: {song.get('beat_confidence')}")
print(f"   Current beat_engines_used: {song.get('beat_engines_used')}")
print(f"   Current beat_needs_review: {song.get('beat_needs_review')}")

# 3. Trigger analysis (this runs the new multi-engine beat detection)
print("\n" + "=" * 60)
print("3. TRIGGER ANALYSIS")
resp = requests.post(f"{BASE}/api/library/songs/{song_id}/analyze", headers=headers)
print(f"   Status: {resp.status_code}")
print(f"   Response: {json.dumps(resp.json(), indent=2, ensure_ascii=False)[:500]}")

# 4. Wait for analysis to complete
print("\n" + "=" * 60)
print("4. WAITING FOR ANALYSIS (checking every 5s, max 120s)...")
for i in range(24):
    time.sleep(5)
    resp = requests.get(f"{BASE}/api/library/songs", headers=headers)
    songs = resp.json().get("data", {}).get("songs", [])
    s = next((x for x in songs if x["id"] == song_id), None)
    if s:
        status = s.get("analysis_status", "unknown")
        print(f"   [{i*5}s] status={status}, bpm={s.get('bpm')}, confidence={s.get('beat_confidence')}, engines={s.get('beat_engines_used')}")
        if status in ("complete", "completed", "done", "analyzed"):
            print("   Analysis complete!")
            song = s
            break
        if status in ("failed", "error"):
            print("   Analysis FAILED!")
            break
else:
    print("   Timed out waiting for analysis.")

# 5. Check needs-review endpoint
print("\n" + "=" * 60)
print("5. NEEDS-REVIEW ENDPOINT")
resp = requests.get(f"{BASE}/api/library/songs/needs-review", headers=headers)
print(f"   Status: {resp.status_code}")
review_data = resp.json()
print(f"   Response: {json.dumps(review_data, indent=2, ensure_ascii=False)[:500]}")

# 6. Test beat correction endpoint
print("\n" + "=" * 60)
print("6. BEAT CORRECTION ENDPOINT")
resp = requests.post(
    f"{BASE}/api/library/songs/{song_id}/correct-beats",
    headers=headers,
    json={"bpm": 128.0, "grid_offset": 0.05, "downbeat_phase": 0},
)
print(f"   Status: {resp.status_code}")
correction_data = resp.json()
print(f"   Response: {json.dumps(correction_data, indent=2, ensure_ascii=False)[:500]}")

# 7. Verify correction persisted
print("\n" + "=" * 60)
print("7. VERIFY CORRECTION")
resp = requests.get(f"{BASE}/api/library/songs", headers=headers)
songs = resp.json().get("data", {}).get("songs", [])
s = next((x for x in songs if x["id"] == song_id), None)
if s:
    print(f"   BPM: {s.get('bpm')}")
    print(f"   beat_confidence: {s.get('beat_confidence')}")
    print(f"   beat_grid_offset: {s.get('beat_grid_offset')}")
    print(f"   beat_grid_interval: {s.get('beat_grid_interval')}")
    print(f"   beat_engines_used: {s.get('beat_engines_used')}")
    print(f"   beat_needs_review: {s.get('beat_needs_review')}")
    print(f"   beat_points count: {len(s.get('beat_points', []))}")

print("\n" + "=" * 60)
print("ALL TESTS DONE!")
