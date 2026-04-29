"""Test stream API performance - measure first-byte and full-download latency."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.shared.database import SessionLocal
from app.shared.models import LibrarySong
import requests

db = SessionLocal()
songs = db.query(LibrarySong).limit(3).all()

if not songs:
    print("No songs found")
    sys.exit(1)

# Get a valid token
from app.shared.auth import create_access_token
token = create_access_token({"sub": "1"})

for song in songs:
    print(f"\n=== {song.title} - {song.artist} ===")
    fp = song.file_path
    if fp and os.path.isfile(fp):
        fsize = os.path.getsize(fp) / 1024 / 1024
        print(f"  File: {fp}")
        print(f"  Size: {fsize:.1f} MB")
    else:
        print(f"  File not found: {fp}")
        continue

    url = f"http://localhost:8000/api/stream/{song.id}?token={token}"

    # Test 1: Full download (what extractPeaks does)
    t0 = time.time()
    resp = requests.get(url, stream=True)
    t_first = time.time() - t0
    data = b""
    for chunk in resp.iter_content(chunk_size=256*1024):
        data += chunk
    t_total = time.time() - t0
    print(f"  Full download: first_byte={t_first*1000:.0f}ms, total={t_total*1000:.0f}ms, downloaded={len(data)/1024/1024:.1f}MB")

    # Test 2: Range request (what <audio> does for metadata)
    t0 = time.time()
    resp2 = requests.get(url, headers={"Range": "bytes=0-32767"}, stream=True)
    t_range = time.time() - t0
    range_data = resp2.content
    print(f"  Range 0-32K: {t_range*1000:.0f}ms, status={resp2.status_code}, size={len(range_data)}")

    # Test 3: Check stems
    if song.stems:
        for stem_name, stem_path in song.stems.items():
            if os.path.isfile(stem_path):
                ssize = os.path.getsize(stem_path) / 1024 / 1024
                stem_url = f"http://localhost:8000/api/stream/{song.id}/stem/{stem_name}?token={token}"
                t0 = time.time()
                sresp = requests.get(stem_url, headers={"Range": "bytes=0-32767"}, stream=True)
                t_stem = time.time() - t0
                print(f"  Stem {stem_name}: size={ssize:.1f}MB, range_time={t_stem*1000:.0f}ms, status={sresp.status_code}")
            break  # test only first stem

db.close()
print("\nDone!")
