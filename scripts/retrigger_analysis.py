"""Re-trigger analysis for songs that have no BPM/Key (analysis was lost due to OOM).

Run inside the container: python /tmp/retrigger_analysis.py
"""
import os
import sys
sys.path.insert(0, "/app")

# Import all models to resolve SQLAlchemy relationships
from app.modules.models import *  # noqa
from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.library.background_tasks import run_analysis_and_separation

db = SessionLocal()
try:
    songs = db.query(LibrarySong).filter(
        LibrarySong.source_path.isnot(None),
        LibrarySong.bpm.is_(None),
    ).all()
    
    print(f"Found {len(songs)} songs needing analysis")
    
    for i, song in enumerate(songs):
        exists = song.source_path and os.path.isfile(song.source_path)
        print(f"  [{i+1}/{len(songs)}] {song.title} - {song.artist} | file_exists={exists} | id={song.id}")
        if exists:
            try:
                run_analysis_and_separation(song.id)
                # Re-read to check result
                db.refresh(song)
                print(f"    => BPM={song.bpm}, Key={song.key}, Duration={song.duration}")
            except Exception as e:
                print(f"    => FAILED: {e}")
        else:
            print(f"    => SKIPPED (no file)")
finally:
    db.close()

print("\nDone!")
