"""End-to-end test: analyze_audio_file() with online BPM lookup + fallback.

Tests TWO songs:
1. California Love (songbpm.com has BPM=91) → should use online fast path
2. Cheshire - ITZY (NOT FOUND on songbpm) → should fall back to local analysis

Usage: PYTHONPATH=. python scripts/_test_e2e_online_bpm.py
"""
import os
import sys
import time

# Load .env
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.isfile(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

import logging
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

from app.modules.library.analysis import analyze_audio_file

MUSIC_DIR = "data/music-files/shared"

TESTS = [
    {
        "file": "California Love - 2Pac _ Dr. Dre _ The D.O.C..mp3",
        "title": "California Love",
        "artist": "2Pac",
        "expect": "online",  # should use songbpm fast path
    },
    {
        "file": "Cheshire - ITZY.mp3",
        "title": "Cheshire",
        "artist": "ITZY",
        "expect": "local",  # not found online, should fall back
    },
]

for test in TESTS:
    filepath = os.path.join(MUSIC_DIR, test["file"])
    if not os.path.isfile(filepath):
        print(f"SKIP: {filepath} not found")
        continue

    print("=" * 70)
    print(f"  {test['title']} - {test['artist']} (expect: {test['expect']})")
    print("=" * 70)

    t0 = time.time()
    result = analyze_audio_file(filepath, title=test["title"], artist=test["artist"])
    elapsed = time.time() - t0

    print(f"\n  Time: {elapsed:.1f}s")
    print(f"  BPM: {result.get('bpm')}")
    print(f"  Key: {result.get('key')} / Camelot: {result.get('camelot_key')}")
    print(f"  Energy: {result.get('energy')}")
    print(f"  Beat engines: {result.get('beat_meta', {}).get('engines_used')}")
    print(f"  Beat confidence: {result.get('beat_meta', {}).get('confidence')}")
    print(f"  Beat points: {len(result.get('beat_points', []))} beats")
    print(f"  Downbeats: {len(result.get('downbeats', []))} downbeats")
    print()
