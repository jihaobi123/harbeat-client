"""Run analysis for ALL pending songs sequentially. Direct execution, no nested subprocess."""
import sys, os, logging, time, traceback
sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s",
                    stream=sys.stdout)

import redis
r = redis.from_url("redis://harbeat-redis:6379/0")
r.delete("harbeat:analysis_lock")
r.delete("harbeat:startup_lock")
print("[trigger] Locks cleared")

from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Song, SongTag
from app.modules.library.background_tasks import run_analysis_and_separation

db = SessionLocal()
# Reset stuck songs
stuck = db.query(LibrarySong).filter(LibrarySong.analysis_status == "analyzing").all()
for s in stuck:
    s.analysis_status = "pending"
    print(f"[trigger] Reset stuck: {s.title}")
db.commit()

pending = db.query(LibrarySong).filter(
    LibrarySong.analysis_status.in_(["pending", "none"])
).all()
to_analyze = [(s.id, s.title, s.artist) for s in pending if s.source_path and os.path.isfile(s.source_path)]
db.close()

print(f"[trigger] {len(to_analyze)} songs to analyze\n")
if not to_analyze:
    print("[trigger] Nothing to do!")
    sys.exit(0)

import gc

def _force_memory_release():
    gc.collect()
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass

success = 0
fail = 0
for i, (song_id, title, artist) in enumerate(to_analyze, 1):
    print(f"[{i}/{len(to_analyze)}] {title} - {artist}")
    sys.stdout.flush()
    start = time.time()
    try:
        run_analysis_and_separation(song_id)
        elapsed = time.time() - start
        print(f"  OK ({elapsed:.1f}s)")
        success += 1
    except Exception as e:
        elapsed = time.time() - start
        print(f"  FAIL ({elapsed:.1f}s): {e}")
        traceback.print_exc()
        fail += 1
    _force_memory_release()
    sys.stdout.flush()

print(f"\nDone! success={success} fail={fail} total={len(to_analyze)}")
