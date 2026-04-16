"""Test beat analysis on a fresh song."""
import json
import requests
import time

BASE = "http://localhost:8000"

# Login
resp = requests.post(f"{BASE}/api/auth/login", json={"username": "qqq", "password": "12345678"})
token = resp.json().get("data", {}).get("access_token", "")
headers = {"Authorization": f"Bearer {token}"}
print(f"Login: {resp.status_code}")

# Find a song without beat_confidence (not yet analyzed with new engine)
resp = requests.get(f"{BASE}/api/library/songs", headers=headers)
songs = resp.json().get("data", {}).get("songs", [])
fresh = [s for s in songs if s.get("beat_confidence") is None]
print(f"Total songs: {len(songs)}, without beat_confidence: {len(fresh)}")

if not fresh:
    print("All songs already analyzed! Picking second song to re-analyze.")
    target = songs[1] if len(songs) > 1 else songs[0]
else:
    target = fresh[0]

song_id = target["id"]
print(f"\nTarget: {target['title']} - {target['artist']} (id={song_id})")
print(f"  BPM: {target.get('bpm')}, confidence: {target.get('beat_confidence')}")

# Trigger analysis
print(f"\nTriggering analysis...")
resp = requests.post(f"{BASE}/api/library/songs/{song_id}/analyze", headers=headers)
print(f"  Status: {resp.status_code}")
body = resp.json()
if resp.status_code != 200:
    print(f"  Error: {body.get('message', '')[:300]}")
else:
    print(f"  Response: {json.dumps(body, indent=2, ensure_ascii=False)[:500]}")

# Wait for result
print(f"\nWaiting for analysis...")
for i in range(30):
    time.sleep(5)
    resp = requests.get(f"{BASE}/api/library/songs", headers=headers)
    songs = resp.json().get("data", {}).get("songs", [])
    s = next((x for x in songs if x["id"] == song_id), None)
    if s:
        st = s.get("analysis_status", "unknown")
        print(f"  [{(i+1)*5}s] status={st}, bpm={s.get('bpm')}, confidence={s.get('beat_confidence')}, engines={s.get('beat_engines_used')}, review={s.get('beat_needs_review')}")
        if st in ("complete", "completed", "done", "analyzed"):
            break
        if st in ("failed", "error"):
            break
else:
    print("  Timed out!")

# Check needs-review endpoint
print(f"\nNeeds-review songs:")
resp = requests.get(f"{BASE}/api/library/songs/needs-review", headers=headers)
print(f"  Status: {resp.status_code}")
review_songs = resp.json().get("data", {}).get("songs", [])
print(f"  Count: {len(review_songs)}")
for s in review_songs[:5]:
    print(f"    {s['title']} - confidence={s.get('beat_confidence')}")

print("\nDone!")
