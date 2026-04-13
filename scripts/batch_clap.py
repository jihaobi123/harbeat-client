"""Batch CLAP audio indexing - runs inside the container.

Usage: docker exec -d harbeat-api python3 /tmp/batch_clap.py
"""
import sys
import os
import time

sys.path.insert(0, '/app')
os.chdir('/app')

from app.modules.models import LibrarySong, Song, SongTag
from app.shared.database import SessionLocal
from app.modules.recommendations.vector_store import index_song_clap, get_clap_collection

db = SessionLocal()

# Get all library songs with files, deduplicate by song_id
lib_songs = (
    db.query(LibrarySong)
    .filter(LibrarySong.source_path.isnot(None), LibrarySong.source_path != "")
    .all()
)

seen = {}
for ls in lib_songs:
    if ls.song_id and ls.song_id not in seen and os.path.isfile(ls.source_path):
        seen[ls.song_id] = ls

# Check what's already indexed
clap_col = get_clap_collection()
existing = set(clap_col.get()["ids"]) if clap_col.count() > 0 else set()

to_index = {sid: ls for sid, ls in seen.items() if str(sid) not in existing}
print(f"Total with files: {len(seen)}, Already indexed: {len(existing)}, To index: {len(to_index)}")
sys.stdout.flush()

success, fail = 0, 0
for i, (song_id, ls) in enumerate(to_index.items(), 1):
    tags = db.query(SongTag).filter(SongTag.song_id == song_id).first()
    
    start = time.time()
    print(f"[{i}/{len(to_index)}] {ls.title} - {ls.artist} ...", end=" ", flush=True)
    
    ok = index_song_clap(
        song_id=str(song_id),
        audio_path=ls.source_path,
        title=ls.title,
        artist=ls.artist,
        style=tags.style if tags else None,
        energy=tags.energy if tags else None,
        groove=tags.groove_tag if tags else None,
        bpm=float(tags.bpm) if tags and tags.bpm else (ls.bpm if ls.bpm else None),
    )
    
    elapsed = time.time() - start
    if ok:
        success += 1
        print(f"OK ({elapsed:.1f}s)")
    else:
        fail += 1
        print(f"FAIL ({elapsed:.1f}s)")
    sys.stdout.flush()

print(f"\nDone! Success: {success}, Failed: {fail}, Total: {len(to_index)}")
db.close()
