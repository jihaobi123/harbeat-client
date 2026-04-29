#!/usr/bin/env python3
import json, urllib.request, sys

base = "http://localhost:8000"

# Login
login_data = json.dumps({"username": "qqq", "password": "12345678"}).encode()
req = urllib.request.Request(f"{base}/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req)
body = json.loads(resp.read())
print("LOGIN RESPONSE:", json.dumps(body, indent=2))

# Extract token
token = body.get("access_token") or body.get("data", {}).get("access_token") or body.get("token") or body.get("data", {}).get("token")
print("TOKEN:", token)

if not token:
    print("ERROR: Could not extract token from login response")
    sys.exit(1)

# DJ mix plan
mix_data = json.dumps({"playlist_id": 8, "duration_minutes": 5, "style": "breaking", "user_id": 8}).encode()
req2 = urllib.request.Request(
    f"{base}/api/playlists/generate-dj-mix-plan",
    data=mix_data,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
)
try:
    resp2 = urllib.request.urlopen(req2, timeout=300)
    result = json.loads(resp2.read())
    print("STATUS:", resp2.status)
    print("PLAYLIST COUNT:", len(result.get("playlist", result.get("data", {}).get("playlist", []))))
    print("RESULT:", json.dumps(result, indent=2)[:2000])
except Exception as e:
    print("ERROR:", e)
    if hasattr(e, 'read'):
        print("BODY:", e.read().decode()[:500])
