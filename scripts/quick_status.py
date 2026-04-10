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
print(f"\nStill need analysis (bpm=None): {len(need)}")
for s in need:
    print(f"  {s.title} | status={s.analysis_status}")

db.close()
