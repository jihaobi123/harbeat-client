"""Fix stuck analysis: release dead lock + reset 'analyzing' songs to 'pending'.

Usage: docker exec harbeat-api python3 /tmp/fix_stuck_analysis.py
"""
import sys
sys.path.insert(0, '/app')

import redis
from app.shared.database import SessionLocal
from app.modules.playlists.models import Song, SongTag  # noqa: ensure models loaded
from app.modules.library.models import LibrarySong

# Step 1: Release the stuck lock
r = redis.from_url("redis://harbeat-redis:6379/0")
lock = r.get("harbeat:analysis_lock")
if lock:
    r.delete("harbeat:analysis_lock")
    print("[fix] Released stuck analysis lock")
else:
    print("[fix] No lock found (already free)")

# Step 2: Reset 'analyzing' songs back to 'pending' so they get re-queued
db = SessionLocal()
stuck = db.query(LibrarySong).filter(LibrarySong.analysis_status == "analyzing").all()
print(f"[fix] Found {len(stuck)} songs stuck in 'analyzing'")
for s in stuck:
    print(f"  Resetting: {s.title} - {s.artist} (id={s.id[:8]}..)")
    s.analysis_status = "pending"
db.commit()

# Step 3: Show current status
pending = db.query(LibrarySong).filter(LibrarySong.analysis_status.in_(["pending", "none"])).count()
print(f"\n[fix] {pending} songs now waiting for analysis")
print("[fix] Restart the container to trigger analysis: docker compose restart app")

db.close()
