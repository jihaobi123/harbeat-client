"""Backfill LibrarySong.vocal_events using the optional GPU vocal detector."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def get_audio_file_path(song: Any) -> str | None:
    source_path = getattr(song, "source_path", None)
    if source_path and os.path.exists(source_path):
        return str(source_path)
    library_id = getattr(song, "id", None)
    for path in (
        f"/mnt/music-files/{library_id}/original.mp3",
        f"/home/mark/music-files/{library_id}/original.mp3",
    ):
        if path and os.path.exists(path):
            return path
    return None


def backfill_vocal_events(
    *,
    library_id: str | None = None,
    song_id: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    fast_mode: bool = False,
    skip_existing: bool = True,
    use_gpu: bool = True,
) -> int:
    from app.modules.library.analysis_vocal_patch_gpu import analyze_vocal_events_gpu
    from app.modules.library.models import LibrarySong
    from app.modules.playlists import models as _playlist_models  # noqa: F401
    from app.shared.database import SessionLocal

    db = SessionLocal()
    success = 0
    failed = 0
    started = time.time()
    try:
        query = db.query(LibrarySong).filter(LibrarySong.phrase_map.isnot(None))
        if library_id:
            query = query.filter(LibrarySong.id == library_id)
        elif song_id:
            query = query.filter(LibrarySong.song_id == song_id)
        elif skip_existing:
            query = query.filter((LibrarySong.vocal_events.is_(None)) | (LibrarySong.vocal_events == []))
        if limit:
            query = query.limit(limit)

        songs = query.all()
        print(f"Found {len(songs)} song(s)")
        for index, song in enumerate(songs, 1):
            elapsed_min = (time.time() - started) / 60.0
            print(f"\n[{index}/{len(songs)}] {song.id} {song.title} elapsed={elapsed_min:.1f}m")
            audio_path = get_audio_file_path(song)
            if not audio_path:
                print("  missing source audio")
                failed += 1
                continue
            try:
                events = analyze_vocal_events_gpu(audio_path, use_gpu=use_gpu, fast_mode=fast_mode)
                print(f"  detected {len(events)} vocal event(s)")
                if dry_run:
                    print("  dry-run: skip write")
                else:
                    song.vocal_events = events
                    db.commit()
                    print("  written")
                success += 1
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failed += 1
                db.rollback()
                print(f"  failed: {exc}")
        print(f"\nDone success={success} failed={failed}")
        return 0 if failed == 0 else 1
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill vocal_events using Demucs GPU")
    parser.add_argument("--library-id", help="LibrarySong.id UUID")
    parser.add_argument("--song-id", help="Catalog LibrarySong.song_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    raise SystemExit(
        backfill_vocal_events(
            library_id=args.library_id,
            song_id=args.song_id,
            dry_run=args.dry_run,
            limit=args.limit,
            fast_mode=args.fast,
            skip_existing=not args.force,
            use_gpu=not args.cpu,
        )
    )


if __name__ == "__main__":
    main()
