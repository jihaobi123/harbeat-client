"""Re-download missing songs and run 3-phase analysis on all library songs.

Usage: docker exec -w /app harbeat-api python3 -u /tmp/redownload_and_analyze.py
"""
import asyncio
import gc
import json
import logging
import os
import platform
import subprocess
import sys
import time

sys.path.insert(0, "/app")

LOG_FILE = "/tmp/redownload_analyze.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("redownload_and_analyze")

from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.library.models import LibrarySong

# ── Phase 0: Re-download missing songs ───────────────────────────────────

async def redownload_missing():
    """Find songs with empty source_path and re-download them."""
    from app.shared.config import get_settings
    from app.modules.fangpi.service import download_fangpi_song

    db = SessionLocal()
    try:
        settings = get_settings()
        upload_dir = os.path.abspath(settings.upload_dir)
        shared_dir = os.path.join(upload_dir, "shared")
        os.makedirs(shared_dir, exist_ok=True)

        missing = db.query(LibrarySong).filter(
            (LibrarySong.source_path == None) | (LibrarySong.source_path == "")
        ).all()

        # Also find songs whose files don't exist on disk
        all_songs = db.query(LibrarySong).filter(
            LibrarySong.source_path != None,
            LibrarySong.source_path != "",
        ).all()
        for s in all_songs:
            if not os.path.isfile(s.source_path):
                missing.append(s)

        if not missing:
            logger.info("No missing songs to re-download!")
            return 0

        logger.info(f"Found {len(missing)} songs needing (re-)download")

        downloaded = 0
        for s in missing:
            logger.info(f"  Downloading: {s.title} - {s.artist} (platform_id={s.platform_id})")
            if not s.platform_id:
                # Try to search for it
                from app.modules.fangpi.service import smart_search_fangpi
                logger.info(f"    No platform_id, searching for '{s.title} {s.artist}'...")
                try:
                    results = await smart_search_fangpi(f"{s.title} {s.artist}")
                    if results:
                        s.platform_id = str(results[0].get("id", results[0].get("music_id", "")))
                        logger.info(f"    Found platform_id: {s.platform_id}")
                    else:
                        logger.warning(f"    No search results, skipping")
                        continue
                except Exception as e:
                    logger.error(f"    Search failed: {e}")
                    continue

            try:
                # Determine source type
                source = s.source_type if hasattr(s, "source_type") and s.source_type else "fangpi"
                result = await download_fangpi_song(
                    s.platform_id, s.title, s.artist, shared_dir,
                    source=source,
                )
                s.source_path = result["file_path"]
                s.file_size = result.get("file_size", 0)
                db.commit()
                downloaded += 1
                logger.info(f"    Downloaded: {result['file_path']} ({result.get('file_size', 0)} bytes)")
            except Exception as e:
                logger.error(f"    Download failed: {e}")
                continue

        return downloaded
    finally:
        db.close()


# ── Analysis helpers ─────────────────────────────────────────────────────

ANALYSIS_LOCK_KEY = "harbeat:analysis_lock"
ANALYSIS_LOCK_TTL = 1800

def acquire_lock(timeout=86400):
    from app.shared.redis import get_redis
    r = get_redis()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if r.set(ANALYSIS_LOCK_KEY, "1", nx=True, ex=ANALYSIS_LOCK_TTL):
            return True
        time.sleep(1)
    return False

def release_lock():
    from app.shared.redis import get_redis
    r = get_redis()
    r.delete(ANALYSIS_LOCK_KEY)

def refresh_lock():
    from app.shared.redis import get_redis
    r = get_redis()
    r.expire(ANALYSIS_LOCK_KEY, ANALYSIS_LOCK_TTL)

def force_memory_release():
    gc.collect()
    if platform.system() == "Linux":
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
        except Exception:
            pass

ANALYSIS_SCRIPT = os.path.join(os.path.dirname(os.path.abspath("/app/app/modules/library/")), "library", "_run_analysis.py")


def run_phase1(file_path):
    """Run BPM/key analysis in subprocess."""
    result = subprocess.run(
        [sys.executable, ANALYSIS_SCRIPT, file_path],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Phase 1 exit={result.returncode} stderr={result.stderr[-500:]}")
    return json.loads(result.stdout)


def run_phase2(source_path, song_id):
    """Run demucs stem separation."""
    stems_base = os.path.abspath(os.path.join(os.path.dirname(source_path), "..", "stems"))
    os.makedirs(stems_base, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(source_path))[0]
    stems_dir = os.path.join(stems_base, "htdemucs", base_name)
    stem_names = ["vocals", "drums", "bass", "other"]

    if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
        logger.info(f"    Phase 2: stems already exist, skipping")
        return {s: os.path.join(stems_dir, f"{s}.wav") for s in stem_names}

    refresh_lock()
    result = subprocess.run(
        [sys.executable, "-m", "demucs", "-n", "htdemucs", "--segment", "7", "-o", stems_base, source_path],
        capture_output=True, text=True, timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError(f"demucs exit={result.returncode} stderr={result.stderr[-800:]}")

    if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
        return {s: os.path.join(stems_dir, f"{s}.wav") for s in stem_names}
    return None


def run_phase3(lib_song, db):
    """Run CLAP audio embedding + ChromaDB indexing."""
    from app.modules.playlists.models import Song as CatalogSong, SongTag
    from app.modules.recommendations.vector_store import index_song_clap, index_song

    catalog_song = db.query(CatalogSong).filter(CatalogSong.id == lib_song.song_id).first() if lib_song.song_id else None
    if not catalog_song:
        logger.warning(f"    Phase 3: no catalog song, skipping")
        return

    tags = db.query(SongTag).filter(SongTag.song_id == catalog_song.id).first()
    refresh_lock()

    ok = index_song_clap(
        song_id=str(catalog_song.id),
        audio_path=lib_song.source_path,
        title=catalog_song.title,
        artist=catalog_song.artist,
        style=tags.style if tags else None,
        energy=tags.energy if tags else None,
        groove=tags.groove_tag if tags else None,
        bpm=float(tags.bpm) if tags and tags.bpm else (lib_song.bpm if lib_song.bpm else None),
    )
    if ok:
        logger.info(f"    Phase 3: CLAP embedding done")
    else:
        logger.warning(f"    Phase 3: CLAP failed, text fallback only")

    index_song(
        song_id=str(catalog_song.id),
        title=catalog_song.title,
        artist=catalog_song.artist,
        style=tags.style if tags else None,
        energy=tags.energy if tags else None,
        groove=tags.groove_tag if tags else None,
        bpm=float(tags.bpm) if tags and tags.bpm else (lib_song.bpm if lib_song.bpm else None),
    )


# ── Main: analyze all songs ─────────────────────────────────────────────

def analyze_all():
    """Run 3-phase analysis on every library song that needs it."""
    db = SessionLocal()
    try:
        all_songs = db.query(LibrarySong).filter(
            LibrarySong.source_path != None,
            LibrarySong.source_path != "",
        ).all()

        stem_names = ["vocals", "drums", "bass", "other"]
        needs_work = []
        for s in all_songs:
            if not os.path.isfile(s.source_path):
                logger.warning(f"Skipping {s.title} - file missing: {s.source_path}")
                continue

            needs_phase1 = s.bpm is None or s.key is None
            stems_base = os.path.abspath(os.path.join(os.path.dirname(s.source_path), "..", "stems"))
            base_name = os.path.splitext(os.path.basename(s.source_path))[0]
            stems_dir = os.path.join(stems_base, "htdemucs", base_name)
            needs_phase2 = not all(os.path.isfile(os.path.join(stems_dir, f"{sn}.wav")) for sn in stem_names)
            # Phase 3 always re-run if source exists (no easy way to check ChromaDB)
            needs_phase3 = True

            if needs_phase1 or needs_phase2:
                needs_work.append((s.id, s.title, s.artist, needs_phase1, needs_phase2))

        # Also add songs that only need phase 3 (have phase1+2 done but might not be in ChromaDB)
        for s in all_songs:
            if not os.path.isfile(s.source_path):
                continue
            sid = s.id
            if not any(w[0] == sid for w in needs_work):
                needs_work.append((s.id, s.title, s.artist, False, False))

        logger.info(f"=== Total library: {len(all_songs)} songs, {len(needs_work)} need work ===")

        for i, (song_id, title, artist, need_p1, need_p2) in enumerate(needs_work, 1):
            song = db.get(LibrarySong, song_id)
            if not song or not song.source_path:
                continue

            work_desc = []
            if need_p1: work_desc.append("P1")
            if need_p2: work_desc.append("P2")
            work_desc.append("P3")

            logger.info(f"\n[{i}/{len(needs_work)}] {title} - {artist} ({'+'.join(work_desc)})")

            try:
                # Phase 1
                if need_p1:
                    logger.info(f"    Phase 1: BPM/key analysis...")
                    result = run_phase1(song.source_path)
                    song.bpm = result["bpm"]
                    song.duration = result["duration"]
                    song.key = result.get("key")
                    song.camelot_key = result.get("camelot_key")
                    song.energy = result.get("energy")
                    song.beat_points = result.get("beat_points", [])
                    song.downbeats = result.get("downbeats", [])
                    song.phrase_map = result.get("phrase_map", [])
                    song.key_confidence = result.get("key_confidence")
                    raw_cues = result.get("cue_points", [])
                    song.cue_points = [
                        {"id": f"cue-{song_id}-{ci}", "time": c["time"], "label": c["label"], "color": c["color"]}
                        for ci, c in enumerate(raw_cues)
                    ]
                    db.commit()
                    logger.info(f"    Phase 1 done: BPM={song.bpm} Key={song.key}")
                    force_memory_release()

                # Phase 2
                if need_p2:
                    logger.info(f"    Phase 2: demucs stem separation...")
                    stems = run_phase2(song.source_path, song_id)
                    if stems:
                        song.stems = stems
                        db.commit()
                        logger.info(f"    Phase 2 done: stems separated")
                    else:
                        logger.warning(f"    Phase 2: stem files not found")
                    force_memory_release()

                # Phase 3
                logger.info(f"    Phase 3: CLAP + ChromaDB indexing...")
                run_phase3(song, db)
                force_memory_release()

                song.analysis_status = "completed"
                db.commit()
                logger.info(f"    All phases done for {title}")

            except Exception as e:
                logger.exception(f"    Error processing {title}: {e}")
                song.analysis_status = "error"
                db.commit()
                force_memory_release()
                continue

        logger.info("\n=== ALL DONE ===")
    finally:
        db.close()


# ── Entry point ──────────────────────────────────────────────────────────

async def main():
    # Step 1: Re-download missing songs
    logger.info("=" * 60)
    logger.info("STEP 1: Re-downloading missing songs...")
    logger.info("=" * 60)
    downloaded = await redownload_missing()
    logger.info(f"Downloaded {downloaded} songs\n")

    # Step 2: Acquire lock and run analysis
    logger.info("=" * 60)
    logger.info("STEP 2: Running 3-phase analysis on all songs...")
    logger.info("=" * 60)

    acquired = acquire_lock(timeout=300)
    if not acquired:
        logger.error("Could not acquire analysis lock! Another analysis may be running.")
        logger.info("Forcibly clearing the lock...")
        release_lock()
        time.sleep(2)
        acquired = acquire_lock(timeout=60)
        if not acquired:
            logger.error("Still can't acquire lock, aborting.")
            return

    try:
        analyze_all()
    finally:
        release_lock()
        force_memory_release()


if __name__ == "__main__":
    asyncio.run(main())
