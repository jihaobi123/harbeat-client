"""Analyze ALL library songs that haven't been fully analyzed (3-phase: BPM/key, demucs, CLAP)."""
import sys, os, gc, ctypes, shutil, time
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, "/app")

from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.library.models import LibrarySong
import redis

db = SessionLocal()
r = redis.Redis(host='harbeat-redis')

# Get all library songs with source files
all_songs = db.query(LibrarySong).filter(LibrarySong.source_path.isnot(None)).all()
print(f"Total library songs with source files: {len(all_songs)}\n")

needs_analysis = []
already_done = []
no_source = []

for song in all_songs:
    has_src = bool(song.source_path and os.path.isfile(song.source_path))
    if not has_src:
        no_source.append(song)
        continue

    has_bpm = song.bpm is not None
    has_stems = bool(song.stems)
    stems_on_disk = False
    if has_stems:
        stems_on_disk = all(os.path.isfile(v) for v in song.stems.values())

    status = song.analysis_status or "none"

    # Need analysis if: not completed, or missing stems, or stems files don't exist on disk
    if status == "completed" and has_bpm and has_stems and stems_on_disk:
        already_done.append(song)
        print(f"  [SKIP] {song.title[:50]:50s} bpm={song.bpm} stems=OK")
    else:
        needs_analysis.append(song)
        print(f"  [TODO] {song.title[:50]:50s} status={status} bpm={song.bpm} stems={has_stems}/{stems_on_disk}")

print(f"\n--- Summary: {len(already_done)} done, {len(needs_analysis)} need analysis, {len(no_source)} no source file ---")

if not needs_analysis:
    print("Nothing to do!")
    db.close()
    sys.exit(0)

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

    # Reset status so all phases re-run
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
total = len(needs_analysis)
for i, song in enumerate(needs_analysis, 1):
    print(f"\n[{i}/{total}] {song.title} - {song.artist}")
    t0 = time.time()
    if run_analysis(song):
        ok += 1
    else:
        fail += 1
    elapsed = time.time() - t0
    print(f"    Time: {elapsed:.0f}s")

print(f"\n=== DONE: {ok} ok, {fail} failed (total {total}) ===")
db.close()
