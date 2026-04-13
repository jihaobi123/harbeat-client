"""Batch stem separation for songs missing stems.

Runs demucs one song at a time, coordinated with API via Redis lock.
Usage: docker exec -w /app harbeat-api python batch_stems.py
"""
import os, sys, subprocess, time
sys.path.insert(0, "/app")

from app.shared.database import SessionLocal
from app.modules.playlists.models import Song
from app.modules.library.models import LibrarySong
from app.modules.library.background_tasks import (
    _acquire_analysis_lock, _release_analysis_lock, _refresh_analysis_lock,
)

db = SessionLocal()

songs = db.query(LibrarySong).filter(
    LibrarySong.analysis_status == "completed",
    LibrarySong.source_path.isnot(None),
).all()

# Find songs without stems that have files on disk
need_stems = []
already_done = 0
no_file = 0

for s in songs:
    if not s.source_path or not os.path.isfile(s.source_path):
        no_file += 1
        continue
    if s.stems:
        # Verify stems actually exist on disk
        stem_names = ["vocals", "drums", "bass", "other"]
        if all(os.path.isfile(s.stems.get(name, "")) for name in stem_names):
            already_done += 1
            continue
    need_stems.append(s)

# Deduplicate by source_path (same file = same stems)
seen_paths = {}
unique_jobs = []
for s in need_stems:
    if s.source_path not in seen_paths:
        seen_paths[s.source_path] = s
        unique_jobs.append(s)

print(f"Total songs: {len(songs)}")
print(f"Already have stems: {already_done}")
print(f"No file on disk: {no_file}")
print(f"Need stem separation: {len(need_stems)} ({len(unique_jobs)} unique files)")

if not unique_jobs:
    print("Nothing to do!")
    db.close()
    sys.exit(0)

success = 0
failed = 0
python_exe = sys.executable

for i, song in enumerate(unique_jobs):
    print(f"\n[{i+1}/{len(unique_jobs)}] {song.title} - {song.artist}")

    stems_base = os.path.join(os.path.dirname(os.path.abspath(song.source_path)), "..", "stems")
    stems_base = os.path.abspath(stems_base)
    os.makedirs(stems_base, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(song.source_path))[0]
    stems_dir = os.path.join(stems_base, "htdemucs", base_name)
    stem_names = ["vocals", "drums", "bass", "other"]

    # Skip if stems already exist on disk
    if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
        print(f"  Stems already exist on disk, updating DB")
        stems_dict = {s: os.path.join(stems_dir, f"{s}.wav") for s in stem_names}
        # Update all copies with the same source_path
        for s2 in need_stems:
            if s2.source_path == song.source_path:
                s2.stems = stems_dict
        db.commit()
        success += 1
        continue

    start = time.time()
    try:
        # Acquire cross-process lock (waits for API tasks to finish)
        print(f"  Waiting for lock...")
        if not _acquire_analysis_lock(timeout=3600):
            print(f"  SKIPPED: could not acquire lock after 1h")
            failed += 1
            continue
        print(f"  Lock acquired, running demucs...")
        _refresh_analysis_lock()  # reset TTL before long run
        result = subprocess.run(
            [python_exe, "-m", "demucs", "-n", "htdemucs", "--segment", "7",
             "-o", stems_base, song.source_path],
            capture_output=True, text=True, timeout=1800,
        )
        elapsed = time.time() - start

        if result.returncode != 0:
            stderr_tail = (result.stderr or "").strip()[-300:]
            print(f"  FAILED ({elapsed:.0f}s): exit={result.returncode} {stderr_tail}")
            failed += 1
            _release_analysis_lock()
            continue

        if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
            stems_dict = {s: os.path.join(stems_dir, f"{s}.wav") for s in stem_names}
            # Update all copies with the same source_path
            for s2 in need_stems:
                if s2.source_path == song.source_path:
                    s2.stems = stems_dict
            db.commit()
            print(f"  OK ({elapsed:.0f}s)")
            success += 1
        else:
            print(f"  FAILED: stem files not found after demucs")
            failed += 1
    except subprocess.TimeoutExpired:
        print(f"  FAILED: timeout (>30min)")
        failed += 1
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1
    finally:
        _release_analysis_lock()

print(f"\n{'='*50}")
print(f"Done! Success={success}, Failed={failed}")
db.close()
