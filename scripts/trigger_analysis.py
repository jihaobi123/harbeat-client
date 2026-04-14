"""Trigger analysis for all pending songs - subprocess-per-song isolation.

Each song is analyzed in a fresh child process so that memory from
madmom/demucs/CLAP is fully released between songs. This prevents the
gradual RSS growth that causes OOM after processing several songs in
the same process.

Usage: docker exec harbeat-api python3 /tmp/trigger_analysis.py
"""
import sys, os, time, subprocess, json
sys.path.insert(0, '/app')

import redis
from app.shared.database import SessionLocal
from app.modules.playlists.models import Song, SongTag
from app.modules.library.models import LibrarySong

# Clean ALL locks
r = redis.from_url("redis://harbeat-redis:6379/0")
r.delete("harbeat:analysis_lock")
r.delete("harbeat:startup_lock")
print("[trigger] Cleared all locks")

# Reset any stuck 'analyzing' songs
db = SessionLocal()
stuck = db.query(LibrarySong).filter(LibrarySong.analysis_status == "analyzing").all()
for s in stuck:
    s.analysis_status = "pending"
    print(f"[trigger] Reset stuck: {s.title}")
db.commit()

# Find all pending songs
pending = db.query(LibrarySong).filter(
    LibrarySong.analysis_status.in_(["pending", "none"])
).all()
to_analyze = [(s.id, s.title, s.artist) for s in pending if s.source_path and os.path.isfile(s.source_path)]
db.close()

print(f"[trigger] {len(to_analyze)} songs to analyze")
if not to_analyze:
    print("[trigger] Nothing to do!")
    sys.exit(0)

# Analyze each song in a FRESH subprocess to prevent memory accumulation
_WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_trigger_one.py")

# Write the per-song worker script inline (avoids needing a separate file)
_WORKER_CODE = '''
import sys, os
sys.path.insert(0, "/app")
song_id = sys.argv[1]
from app.modules.library.background_tasks import run_analysis_and_separation
run_analysis_and_separation(song_id)
'''

worker_path = "/tmp/_trigger_one.py"
with open(worker_path, "w") as f:
    f.write(_WORKER_CODE)

success = 0
fail = 0
for i, (song_id, title, artist) in enumerate(to_analyze, 1):
    print(f"\n[{i}/{len(to_analyze)}] {title} - {artist} (id={song_id})")
    sys.stdout.flush()
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, worker_path, song_id],
            capture_output=True, text=True,
            timeout=3600,  # 1h max per song
        )
        elapsed = time.time() - start
        if result.returncode == 0:
            print(f"  OK ({elapsed:.1f}s)")
            success += 1
        else:
            stderr_tail = (result.stderr or "").strip()[-500:]
            print(f"  FAIL exit={result.returncode} ({elapsed:.1f}s): {stderr_tail}")
            fail += 1
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"  TIMEOUT ({elapsed:.1f}s)")
        fail += 1
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ERROR ({elapsed:.1f}s): {e}")
        fail += 1
    sys.stdout.flush()

print(f"\nDone! success={success} fail={fail} total={len(to_analyze)}")
