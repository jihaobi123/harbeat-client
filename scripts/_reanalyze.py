"""Reanalyze Fired Up via API to update DB with fixed BPM."""
import requests, json

BASE = "http://localhost:8000"
# Login
r = requests.post(f"{BASE}/api/auth/login", json={"username": "qqq", "password": "12345678"})
token = r.json()["data"]["access_token"]
print(f"Login: {r.status_code}")

# Trigger re-analysis  
r2 = requests.post(
    f"{BASE}/api/library/songs/facf379ec8194c2eb4c5a80858db4957/analyze",
    headers={"Authorization": f"Bearer {token}"}
)
d = r2.json()
print(f"Analyze: {r2.status_code}")
if d.get("data"):
    print(f"  BPM: {d['data'].get('bpm')}")
    print(f"  Beat confidence: {d['data'].get('beat_confidence')}")
    print(f"  Engines: {d['data'].get('beat_engines_used')}")
else:
    print(f"  Response: {json.dumps(d, ensure_ascii=False)[:300]}")
