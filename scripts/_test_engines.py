"""Test analysis with all 3 engines on a different song."""
import json
import requests
import time

BASE = "http://localhost:8000"

resp = requests.post(f"{BASE}/api/auth/login", json={"username": "qqq", "password": "12345678"})
token = resp.json()["data"]["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get songs without beat_confidence 
resp = requests.get(f"{BASE}/api/library/songs", headers=headers)
songs = resp.json()["data"]["songs"]
fresh = [s for s in songs if s.get("beat_confidence") is None]
print(f"Songs without beat_confidence: {len(fresh)}")

if not fresh:
    print("No fresh songs!")
    exit(0)

# Pick a second song
target = fresh[1] if len(fresh) > 1 else fresh[0]
song_id = target["id"]
print(f"Target: {target['title']} - {target['artist']} (id={song_id})")

# Trigger
resp = requests.post(f"{BASE}/api/library/songs/{song_id}/analyze", headers=headers)
print(f"Analyze status: {resp.status_code}")
if resp.status_code != 200:
    print(f"Error: {resp.json().get('message', '')[:500]}")
    exit(1)

data = resp.json().get("data", {})
print(f"BPM: {data.get('bpm')}")
print(f"Confidence: {data.get('beat_confidence')}")
print(f"Engines: {data.get('beat_engines_used')}")
print(f"Grid offset: {data.get('beat_grid_offset')}")
print(f"Grid interval: {data.get('beat_grid_interval')}")
print(f"Needs review: {data.get('beat_needs_review')}")
print(f"Beat points count: {len(data.get('beat_points', []))}")
print(f"First 5 beats: {data.get('beat_points', [])[:5]}")
