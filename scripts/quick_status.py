"""Quick DB status check after restart."""
import os, sys
sys.path.insert(0, "/app")
from app.modules.models import *  # noqa
from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong

db = SessionLocal()
songs = db.query(LibrarySong).all()

counts = {}
for s in songs:
    st = s.analysis_status or "none"
    counts[st] = counts.get(st, 0) + 1
print(f"Total: {len(songs)}, Status: {counts}")

has_bpm = sum(1 for s in songs if s.bpm is not None)
has_key = sum(1 for s in songs if s.key is not None)
has_stems = sum(1 for s in songs if s.stems)
print(f"Has BPM: {has_bpm}, Has Key: {has_key}, Has Stems: {has_stems}")

need = [s for s in songs if s.bpm is None and s.source_path and os.path.isfile(s.source_path)]
analyzing = [s for s in songs if s.analysis_status == "analyzing"]
pending = [s for s in songs if s.analysis_status in ("pending", "none")]
no_file = [s for s in songs if not s.source_path or not os.path.isfile(s.source_path or "")]

print(f"\nAnalyzing: {len(analyzing)}")
for s in analyzing:
    print(f"  {s.title[:40]} | bpm={s.bpm}")

print(f"\nPending: {len(pending)}")
for s in pending:
    has_file = "OK" if s.source_path and os.path.isfile(s.source_path) else "NO"
    print(f"  {s.title[:40]} | file={has_file}")

print(f"\nNeed analysis (bpm=None + file OK): {len(need)}")
for s in need[:20]:
    print(f"  {s.title[:40]} | status={s.analysis_status}")

print(f"\nNo file: {len(no_file)}")

# Check redis lock
try:
    from app.shared.redis import get_redis
    r = get_redis()
    lock = r.get("harbeat:analysis_lock")
    print(f"\nAnalysis lock: {'LOCKED' if lock else 'FREE'}")
except Exception:
    pass

db.close()
