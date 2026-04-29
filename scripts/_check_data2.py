import urllib.request, json, sys

def test(base, label):
    login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(f"{base}/api/auth/login", data=login_data,
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req)
        d = json.loads(r.read())
        token = d.get("data", {}).get("access_token", "")
        print(f"[{label}] Login OK, token={'present' if token else 'missing'}")
        return token
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[{label}] Login FAILED: {e.code} {body[:200]}")
        return None

# Test direct to Jetson via Tailscale
t1 = test("http://100.91.30.53:8000", "Direct-Jetson")

# Test via gateway
t2 = test("http://127.0.0.1:8080", "Gateway")

# Test via Nginx
t3 = test("http://127.0.0.1:80", "Nginx")

# If any token works, check songs
token = t1 or t2 or t3
if token:
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib.request.Request("http://100.91.30.53:8000/api/library/songs?limit=3", headers=headers)
    try:
        r = urllib.request.urlopen(req)
        d = json.loads(r.read())
        items = d.get("data", {}).get("items", d.get("data", []))
        if isinstance(items, list):
            print(f"\nSongs: {len(items)} returned")
            for s in items[:3]:
                print(f"  - {s.get('title','?')} | BPM: {s.get('bpm','?')}")
        else:
            print(f"\nSongs: {str(d)[:300]}")
    except Exception as e:
        print(f"\nSongs: {e}")
