"""Re-download songs whose audio files are missing from disk.

Run inside the container: docker exec -w /app harbeat-api python redownload_missing.py

For each song with a missing file:
1. Try to download via Kuwo (fangpi is blocked by Cloudflare)
2. Update file_size and source_path
3. Reset analysis_status to "pending" so background tasks pick it up
"""
import asyncio
import os
import sys
import re
import logging

sys.path.insert(0, "/app")
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

from app.shared.database import SessionLocal
from app.modules.models import *  # noqa: load all models
from app.modules.library.models import LibrarySong


async def redownload_one(song: LibrarySong, dest_dir: str) -> bool:
    """Try to re-download a single song. Returns True on success."""
    from app.modules.fangpi.service import download_fangpi_song

    # Use platform_id if available, otherwise generate a dummy one
    music_id = song.platform_id or "0"
    source = "kuwo"  # fangpi is blocked, go straight to kuwo

    try:
        result = await download_fangpi_song(
            music_id=music_id,
            title=song.title,
            artist=song.artist,
            dest_dir=dest_dir,
            source=source,  # force kuwo search by title+artist
        )
        return result
    except Exception as e:
        logger.error(f"  FAILED: {e}")
        return None


async def main():
    db = SessionLocal()
    try:
        # Find all songs with missing files
        songs = db.query(LibrarySong).filter(
            LibrarySong.analysis_status == "completed",
            LibrarySong.source_path.isnot(None),
        ).all()

        missing = []
        for s in songs:
            if not s.source_path or not os.path.isfile(s.source_path):
                missing.append(s)

        # Deduplicate: group by title+artist, pick one per group
        seen = {}
        unique_missing = []
        for s in missing:
            key = (s.title.lower().strip(), s.artist.lower().strip())
            if key not in seen:
                seen[key] = s
                unique_missing.append(s)

        print(f"Total songs: {len(songs)}")
        print(f"Missing files: {len(missing)} ({len(unique_missing)} unique)")

        if not unique_missing:
            print("Nothing to do!")
            return

        dest_dir = "/app/data/music-files/shared"
        os.makedirs(dest_dir, exist_ok=True)

        success = 0
        failed = 0
        skipped = 0

        for i, song in enumerate(unique_missing):
            print(f"\n[{i+1}/{len(unique_missing)}] {song.title} - {song.artist}")

            # Check if the expected file already exists (maybe another user's copy was there)
            safe_name = re.sub(r'[<>:"/\\|?*]', "_", f"{song.title} - {song.artist}")[:200]
            expected_path = os.path.join(dest_dir, f"{safe_name}.mp3")

            if os.path.isfile(expected_path) and os.path.getsize(expected_path) > 200_000:
                print(f"  File already exists: {expected_path}")
                # Update path for all copies of this song
                key = (song.title.lower().strip(), song.artist.lower().strip())
                all_copies = [s for s in missing if (s.title.lower().strip(), s.artist.lower().strip()) == key]
                for copy in all_copies:
                    copy.source_path = expected_path
                    copy.file_size = os.path.getsize(expected_path)
                db.commit()
                skipped += 1
                continue

            result = await redownload_one(song, dest_dir)
            if result:
                file_path = result["file_path"]
                file_size = result["file_size"]
                print(f"  OK: {file_size / 1024:.0f} KB -> {file_path}")

                # Update ALL copies of this song (same title+artist, different users)
                key = (song.title.lower().strip(), song.artist.lower().strip())
                all_copies = [s for s in missing if (s.title.lower().strip(), s.artist.lower().strip()) == key]
                for copy in all_copies:
                    copy.source_path = file_path
                    copy.file_size = file_size
                    # Reset analysis for cue point re-detection
                    if len(copy.cue_points or []) <= 1:
                        copy.analysis_status = "pending"
                db.commit()
                success += 1

                # Small delay between downloads to avoid rate limiting
                await asyncio.sleep(2)
            else:
                failed += 1

        print(f"\n{'='*50}")
        print(f"Done! Success={success}, Already existed={skipped}, Failed={failed}")
        print(f"Songs needing re-analysis will be picked up by background tasks on next restart")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
