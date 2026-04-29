"""Debug: run analysis on ONE song with full output."""
import sys, os, logging, traceback
sys.path.insert(0, "/app")

# Enable ALL logging
logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s",
                    stream=sys.stdout)

import redis
r = redis.from_url("redis://harbeat-redis:6379/0")
r.delete("harbeat:analysis_lock")
r.delete("harbeat:startup_lock")
print("=== Locks cleared ===\n")

from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Song

db = SessionLocal()
# Pick first song without BPM
song = db.query(LibrarySong).filter(
    LibrarySong.analysis_status.in_(["pending", "none"]),
    LibrarySong.bpm == None
).first()

if not song:
    print("No pending songs without BPM!")
    sys.exit(0)

print(f"=== Testing: {song.title} - {song.artist} ===")
print(f"  id={song.id}")
print(f"  source_path={song.source_path}")
print(f"  file_exists={os.path.isfile(song.source_path) if song.source_path else False}")
print(f"  bpm={song.bpm}, key={song.key}, status={song.analysis_status}")
print()
db.close()

# Now run analysis with full tracing
print("=== Running run_analysis_and_separation ===")
try:
    from app.modules.library.background_tasks import run_analysis_and_separation
    run_analysis_and_separation(song.id)
    print("\n=== Returned OK ===")
except Exception:
    print("\n=== EXCEPTION ===")
    traceback.print_exc()

# Check result
db2 = SessionLocal()
song2 = db2.get(LibrarySong, song.id)
print(f"\n=== After: status={song2.analysis_status}, bpm={song2.bpm}, key={song2.key} ===")
db2.close()
