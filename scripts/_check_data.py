import urllib.request, json

BASE = "http://localhost"

# 1. Login
login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request(f"{BASE}/api/auth/login", data=login_data,
                             headers={"Content-Type": "application/json"})
try:
    r = urllib.request.urlopen(req)
    d = json.loads(r.read())
    token = d.get("data", {}).get("access_token", "")
    print(f"Login: code={d.get('code')} token={'OK' if token else 'MISSING'}")
except Exception as e:
    # try different login format
    login_data2 = json.dumps({"email": "admin@harbeat.com", "password": "admin123"}).encode()
    req2 = urllib.request.Request(f"{BASE}/api/auth/login", data=login_data2,
                                  headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req2)
        d = json.loads(r.read())
        token = d.get("data", {}).get("access_token", "")
        print(f"Login (email): code={d.get('code')} token={'OK' if token else 'MISSING'}")
    except Exception as e2:
        print(f"Login failed: {e2}")
        token = ""

if not token:
    print("Cannot proceed without token")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

# 2. Songs
req = urllib.request.Request(f"{BASE}/api/library/songs?limit=5", headers=headers)
try:
    r = urllib.request.urlopen(req)
    d = json.loads(r.read())
    items = d.get("data", {}).get("items", d.get("data", []))
    if isinstance(items, list):
        print(f"\nSongs: {len(items)} returned")
        for s in items[:5]:
            print(f"  - {s.get('title','?')} | BPM: {s.get('bpm','?')} | file: {s.get('file_path','?')[:50]}")
    else:
        print(f"\nSongs data: {str(d)[:300]}")
except Exception as e:
    print(f"\nSongs error: {e}")

# 3. Users/me
req = urllib.request.Request(f"{BASE}/api/users/me", headers=headers)
try:
    r = urllib.request.urlopen(req)
    d = json.loads(r.read())
    print(f"\nUser: {d.get('data', {}).get('username', '?')} | email: {d.get('data', {}).get('email', '?')}")
except Exception as e:
    print(f"\nUser error: {e}")

# 4. Playlists
req = urllib.request.Request(f"{BASE}/api/playlists", headers=headers)
try:
    r = urllib.request.urlopen(req)
    d = json.loads(r.read())
    items = d.get("data", [])
    if isinstance(items, list):
        print(f"\nPlaylists: {len(items)}")
    else:
        print(f"\nPlaylists: {str(d)[:200]}")
except Exception as e:
    print(f"\nPlaylists error: {e}")
