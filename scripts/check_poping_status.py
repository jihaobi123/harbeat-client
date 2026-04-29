"""Check poping playlist songs and all pending songs."""
import sys
sys.path.insert(0, '/app')

from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Song, SongTag, Playlist, PlaylistSong

db = SessionLocal()

# Find playlists with "poping" in name
print("=== PLAYLISTS ===")
playlists = db.query(Playlist).all()
for p in playlists:
    count = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == p.id).count()
    print(f"  Playlist ID={p.id} | name='{p.playlist_name}' | songs={count}")

print()

# Find songs with popping style tag
print("=== SONGS WITH POPPING/POPING STYLE ===")
popping_tags = db.query(SongTag).filter(SongTag.style.like('%pop%')).all()
for tag in popping_tags:
    song = db.query(Song).filter(Song.id == tag.song_id).first()
    lib = db.query(LibrarySong).filter(LibrarySong.song_id == tag.song_id).first()
    if song:
        status = lib.analysis_status if lib else "no_library_entry"
        has_file = bool(lib.source_path) if lib else False
        print(f"  song_id={song.id} | {song.title} - {song.artist}")
        print(f"    style={tag.style} | analysis={status} | file={has_file}")
        if lib:
            print(f"    bpm={lib.bpm} | key={lib.key} | stems={bool(lib.stems)} | beats={bool(lib.beat_points)}")

print()

# All pending/none/error analysis songs
print("=== ALL PENDING/NONE/ERROR STATUS SONGS ===")
pending = db.query(LibrarySong).filter(LibrarySong.analysis_status.in_(['pending', 'none', 'error', 'analyzing'])).all()
print(f"Total non-completed songs: {len(pending)}")
for s in pending:
    tag = db.query(SongTag).filter(SongTag.song_id == s.song_id).first() if s.song_id else None
    print(f"  ID={s.id[:8]}.. | song_id={s.song_id} | {s.title} - {s.artist}")
    print(f"    status={s.analysis_status} | file={bool(s.source_path)} | size={s.file_size}")
    if tag:
        print(f"    tag: style={tag.style}")

print()

# Summary
total = db.query(LibrarySong).count()
completed = db.query(LibrarySong).filter(LibrarySong.analysis_status == 'completed').count()
pending_count = db.query(LibrarySong).filter(LibrarySong.analysis_status == 'pending').count()
error_count = db.query(LibrarySong).filter(LibrarySong.analysis_status == 'error').count()
none_count = db.query(LibrarySong).filter(LibrarySong.analysis_status == 'none').count()
analyzing_count = db.query(LibrarySong).filter(LibrarySong.analysis_status == 'analyzing').count()
with_stems = db.query(LibrarySong).filter(LibrarySong.stems.isnot(None)).count()

print(f"=== SUMMARY ===")
print(f"Total songs: {total}")
print(f"  completed: {completed}")
print(f"  pending: {pending_count}")
print(f"  analyzing: {analyzing_count}")
print(f"  error: {error_count}")
print(f"  none: {none_count}")
print(f"  with_stems: {with_stems}")

# Check redis analysis lock
import redis
r = redis.from_url("redis://harbeat-redis:6379/0")
lock = r.get("harbeat:analysis_lock")
print(f"\nAnalysis lock: {'LOCKED' if lock else 'FREE'}")

db.close()
