import requests, json
# Test through nginx (port 80) - same as browser
resp = requests.post("http://localhost:80/api/auth/login", json={"username": "qqq", "password": "12345678"})
print(f"nginx (80): {resp.status_code} -> {json.dumps(resp.json(), ensure_ascii=False)[:200]}")

# Test direct (port 8000)
resp2 = requests.post("http://localhost:8000/api/auth/login", json={"username": "qqq", "password": "12345678"})
print(f"direct (8000): {resp2.status_code} -> {json.dumps(resp2.json(), ensure_ascii=False)[:200]}")
