"""Check which songs need analysis or stem separation."""
import os, sys
sys.path.insert(0, '/home/mark/harbeat')
os.chdir('/home/mark/harbeat')

from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Song, SongTag

db = SessionLocal()
songs = db.query(LibrarySong).all()

need_full = []
need_stems = []

for s in songs:
    hs = bool(s.stems)
    hb = s.bpm is not None
    hf = s.source_path and os.path.isfile(s.source_path)
    if not hb and hf:
        need_full.append(s.id)
    elif hb and not hs and hf:
        need_stems.append(s.id)

db.close()

print(f"Need full analysis (no BPM): {len(need_full)}")
for x in need_full:
    print(f"  full: {x[:8]}")
print(f"Need stems only (has BPM, no stems): {len(need_stems)}")
for x in need_stems:
    print(f"  stems: {x[:8]}")

# Now trigger analysis
if need_full or need_stems:
    from app.modules.library.background_tasks import run_analysis_and_separation
    all_ids = need_full + need_stems
    print(f"\nTriggering analysis for {len(all_ids)} songs...")
    for i, sid in enumerate(all_ids):
        print(f"[{i+1}/{len(all_ids)}] Processing {sid[:8]}...")
        try:
            run_analysis_and_separation(sid)
            print(f"  OK: {sid[:8]}")
        except Exception as e:
            print(f"  FAIL: {sid[:8]}: {e}")
    print("All done.")
else:
    print("Nothing to do.")
