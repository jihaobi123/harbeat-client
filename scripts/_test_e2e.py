import httpx, sys

# Test full flow: Register -> Login -> Access playlists -> Access library
# Tests 3 paths: Direct Jetson, Gateway, Nginx

PATHS = {
    "Direct-Jetson": "http://100.91.30.53:8000",
    "Gateway-8080": "http://127.0.0.1:8080",
    "Nginx-80": "http://127.0.0.1",
}

user = {"username": "testflow", "password": "Test1234"}

for name, base in PATHS.items():
    print(f"\n{'='*40}")
    print(f"=== {name} ({base}) ===")
    print(f"{'='*40}")
    
    # Register (may fail if already exists, that's ok)
    r = httpx.post(f"{base}/api/auth/register", json=user, timeout=10)
    print(f"[Register] {r.status_code}: {r.text[:150]}")
    
    # Login
    r = httpx.post(f"{base}/api/auth/login", json=user, timeout=10)
    print(f"[Login] {r.status_code}: {r.text[:150]}")
    
    if r.status_code == 200:
        data = r.json()
        token = data.get("data", {}).get("access_token")
        if token:
            headers = {"Authorization": f"Bearer {token}"}
            
            # Get playlists
            r2 = httpx.get(f"{base}/api/playlists/", headers=headers, timeout=10)
            print(f"[Playlists] {r2.status_code}: {r2.text[:200]}")
            
            # Get library
            r3 = httpx.get(f"{base}/api/library/songs", headers=headers, timeout=10)
            print(f"[Library] {r3.status_code}: {r3.text[:200]}")
            
            # Health
            r4 = httpx.get(f"{base}/health", timeout=10)
            print(f"[Health] {r4.status_code}: {r4.text[:100]}")
        else:
            print("No token found")
    
    # Only register once (on first path)
    user_registered = True
