"""Minimal login test."""
import requests
import json

BASE = "http://localhost:8000"
payload = {"username": "qqq", "password": "12345678"}

resp = requests.post(f"{BASE}/api/auth/login", json=payload)
print(f"Status: {resp.status_code}")
print(f"Body: {json.dumps(resp.json(), indent=2, ensure_ascii=False)[:500]}")
