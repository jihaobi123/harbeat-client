"""Re-separate all stems using --segment 7 (improved quality over segment 4).

Usage: docker exec harbeat-api python3 /tmp/reseparate_stems.py [--dry-run]

This deletes existing stems and re-runs demucs with --segment 7 for better quality.
Processes songs one-by-one with memory cleanup between each.
"""
import os
import sys
import gc
import shutil
import subprocess
import ctypes
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

STEMS_BASE = "/app/data/music-files/stems"
SHARED_DIR = "/app/data/music-files/shared"
STEM_NAMES = ["vocals", "drums", "bass", "other"]
DRY_RUN = "--dry-run" in sys.argv


def _force_memory_release():
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def find_songs_with_stems():
    """Find all songs that have existing stems."""
    htdemucs_dir = os.path.join(STEMS_BASE, "htdemucs")
    if not os.path.isdir(htdemucs_dir):
        return []

    songs = []
    for name in sorted(os.listdir(htdemucs_dir)):
        stem_dir = os.path.join(htdemucs_dir, name)
        if not os.path.isdir(stem_dir):
            continue
        has_all = all(os.path.isfile(os.path.join(stem_dir, f"{s}.wav")) for s in STEM_NAMES)
        # Find source file
        source = None
        for ext in [".mp3", ".flac", ".wav", ".m4a", ".ogg"]:
            candidate = os.path.join(SHARED_DIR, name + ext)
            if os.path.isfile(candidate):
                source = candidate
                break
        songs.append({
            "name": name,
            "stem_dir": stem_dir,
            "source": source,
            "has_all_stems": has_all,
        })
    return songs


def reseparate(song):
    """Delete old stems and re-run demucs."""
    name = song["name"]
    stem_dir = song["stem_dir"]
    source = song["source"]

    if not source:
        logger.warning("  SKIP %s: no source file found", name)
        return False

    if DRY_RUN:
        logger.info("  [DRY-RUN] would re-separate: %s", name)
        return True

    # Delete old stems
    logger.info("  Deleting old stems: %s", stem_dir)
    shutil.rmtree(stem_dir, ignore_errors=True)

    # Run demucs
    logger.info("  Running demucs --segment 7 on: %s", os.path.basename(source))
    result = subprocess.run(
        [sys.executable, "-m", "demucs", "-n", "htdemucs", "--segment", "7",
         "-o", STEMS_BASE, source],
        capture_output=True,
        text=True,
        timeout=1800,
    )

    _force_memory_release()

    if result.returncode != 0:
        logger.error("  FAILED: %s", (result.stderr or "")[-500:])
        return False

    # Verify output
    if all(os.path.isfile(os.path.join(stem_dir, f"{s}.wav")) for s in STEM_NAMES):
        logger.info("  OK: all 4 stems created")
        return True
    else:
        logger.error("  PARTIAL: some stems missing after demucs")
        return False


def main():
    songs = find_songs_with_stems()
    logger.info("Found %d songs with stems directory", len(songs))

    if DRY_RUN:
        logger.info("=== DRY RUN MODE ===")

    ok = 0
    fail = 0
    skip = 0
    for i, song in enumerate(songs, 1):
        logger.info("[%d/%d] %s", i, len(songs), song["name"])
        if not song["source"]:
            skip += 1
            logger.warning("  SKIP: no source file")
            continue
        if reseparate(song):
            ok += 1
        else:
            fail += 1

    logger.info("Done: %d ok, %d failed, %d skipped (total %d)", ok, fail, skip, len(songs))


if __name__ == "__main__":
    main()
