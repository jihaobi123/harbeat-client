"""Check breaking playlist and re-analyze all songs with --segment 7."""
import sys, os, gc, ctypes, subprocess, shutil, time
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, "/app")

from app.shared.config import get_settings
from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Playlist, PlaylistSong, Song
import redis

db = SessionLocal()
r = redis.Redis(host='harbeat-redis')

# Find breaking playlist
playlists = db.query(Playlist).filter(Playlist.playlist_name.ilike("%breaking%")).all()
if not playlists:
    print("No breaking playlist found!")
    db.close()
    sys.exit(1)

pl = playlists[0]
print(f"Playlist: {pl.playlist_name} (id={pl.id})")

# Get playlist songs -> catalog songs -> library songs
items = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == pl.id).order_by(PlaylistSong.order_index).all()
catalog_ids = [item.song_id for item in items]

lib_songs = db.query(LibrarySong).filter(LibrarySong.song_id.in_(catalog_ids)).all()
print(f"Total library songs: {len(lib_songs)}\n")

needs_analysis = []
for song in lib_songs:
    has_src = bool(song.source_path and os.path.isfile(song.source_path))
    has_stems = bool(song.stems)
    stems_disk = False
    if has_stems:
        stems_disk = all(os.path.isfile(v) for v in song.stems.values())
    status = song.analysis_status or "none"
    print(f"  [{status:10s}] {song.title[:45]:45s} src={has_src} stems={has_stems}/{stems_disk} bpm={song.bpm}")
    if has_src:
        needs_analysis.append(song)

print(f"\n--- {len(needs_analysis)} songs with source files, will re-analyze all ---")

# Clear stale lock
r.delete('harbeat:analysis_lock')
print("Cleared analysis lock\n")

def _force_memory_release():
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

def run_analysis(song):
    """Run full 3-phase analysis for a single song."""
    from app.modules.library.background_tasks import _do_analysis_and_separation
    
    # Reset status so Phase 1 re-runs
    song.analysis_status = "analyzing"
    song.bpm = None
    song.key = None
    song.energy = None
    song.stems = None
    song.beat_points = []
    song.cue_points = []
    song.downbeats = []
    song.phrase_map = []
    
    # Delete old stems if they exist
    if song.source_path:
        base_name = os.path.splitext(os.path.basename(song.source_path))[0]
        stems_dir = os.path.join(os.path.dirname(os.path.abspath(song.source_path)), "..", "stems", "htdemucs", base_name)
        stems_dir = os.path.abspath(stems_dir)
        if os.path.isdir(stems_dir):
            shutil.rmtree(stems_dir, ignore_errors=True)
            print(f"    Deleted old stems")
    
    db.commit()
    
    try:
        _do_analysis_and_separation(song.id)
        # Refresh from DB to get updated values
        db.refresh(song)
        print(f"    Done! status={song.analysis_status} bpm={song.bpm} stems={bool(song.stems)}")
        return True
    except Exception as e:
        db.rollback()
        song.analysis_status = "failed"
        db.commit()
        print(f"    FAILED: {e}")
        return False
    finally:
        _force_memory_release()

ok = 0
fail = 0
for i, song in enumerate(needs_analysis, 1):
    print(f"\n[{i}/{len(needs_analysis)}] {song.title} - {song.artist}")
    t0 = time.time()
    if run_analysis(song):
        ok += 1
    else:
        fail += 1
    elapsed = time.time() - t0
    print(f"    Time: {elapsed:.0f}s")

print(f"\n=== DONE: {ok} ok, {fail} failed (total {len(needs_analysis)}) ===")
db.close()
