#!/usr/bin/env python3
"""Re-run stem separation for songs that have BPM but no stems."""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong

db = SessionLocal()
songs = db.query(LibrarySong).all()
need_stems = []
for s in songs:
    has_stems = bool(s.stems)
    has_bpm = s.bpm is not None
    has_file = s.source_path and os.path.isfile(s.source_path)
    print(f"  {s.id[:8]}  bpm={s.bpm}  stems={has_stems}  file={has_file}  {s.title}")
    if has_bpm and not has_stems and has_file:
        need_stems.append(s.id)
db.close()

print(f"\n{len(need_stems)} songs need stem separation")

if need_stems:
    from app.modules.library.background_tasks import run_analysis_and_separation
    for sid in need_stems:
        print(f"Queuing stem separation for {sid[:8]}...")
        try:
            run_analysis_and_separation(sid)
            print(f"  Done: {sid[:8]}")
        except Exception as e:
            print(f"  Failed: {sid[:8]}: {e}")
