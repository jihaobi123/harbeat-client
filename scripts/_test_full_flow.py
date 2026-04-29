import httpx, sys

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://100.91.30.53:8000"

# Login
r = httpx.post(f"{BASE}/api/auth/login", json={"username": "qq", "password": "123456"})
print(f"[Login] {r.status_code}: {r.text[:200]}")

if r.status_code == 200:
    token = r.json().get("data", {}).get("access_token")
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        r2 = httpx.get(f"{BASE}/api/playlists/", headers=headers)
        print(f"[Playlists] {r2.status_code}: {r2.text[:300]}")
        r3 = httpx.get(f"{BASE}/api/library/songs", headers=headers)
        print(f"[Library] {r3.status_code}: {r3.text[:300]}")
    else:
        print("No token in response")
else:
    print("Login failed, trying other users...")
    for u in ["jihaobi", "enddie", "Ryan", "qqq"]:
        r = httpx.post(f"{BASE}/api/auth/login", json={"username": u, "password": "123456"})
        print(f"  [{u}] {r.status_code}: {r.text[:100]}")
