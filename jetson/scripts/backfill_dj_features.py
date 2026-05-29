"""Backfill: run dj_feature_extractor on every analyzed LibrarySong that
doesn't yet have music_features['dj'] (or whose stored version is older).

Idempotent — re-running just skips songs that are already up-to-date.

Usage:
    cd /home/mark/harbeat
    ~/venvs/harbeat/bin/python scripts/backfill_dj_features.py            # all users
    ~/venvs/harbeat/bin/python scripts/backfill_dj_features.py --user 1   # one user
    ~/venvs/harbeat/bin/python scripts/backfill_dj_features.py --limit 5  # smoke
"""
from __future__ import annotations

import argparse
import sys
import time
import os

# Add repo root so `app.*` imports resolve when invoked from anywhere.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app  # noqa: F401  (loads all model registrations)
from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.library.dj_feature_extractor import (
    extract_dj_features,
    update_library_song_dj_features,
    FEATURE_VERSION,
)


def needs_refresh(song) -> bool:
    mf = song.music_features or {}
    dj = mf.get("dj") if isinstance(mf, dict) else None
    if not dj:
        return True
    return int(dj.get("version", 0)) < FEATURE_VERSION


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true",
                        help="re-extract even when version is current")
    args = parser.parse_args()

    db = SessionLocal()
    q = db.query(LibrarySong).filter(LibrarySong.bpm.isnot(None))
    if args.user is not None:
        q = q.filter(LibrarySong.user_id == args.user)
    songs = q.order_by(LibrarySong.created_at.asc()).all()

    todo = [s for s in songs if args.force or needs_refresh(s)]
    if args.limit:
        todo = todo[: args.limit]
    print(f"backfill: {len(todo)} songs (of {len(songs)} analyzed)")

    ok = 0
    failed = 0
    t0 = time.time()
    for i, song in enumerate(todo, 1):
        try:
            t1 = time.time()
            feats = extract_dj_features(song)
            update_library_song_dj_features(db, song, feats)
            print(f"[{i}/{len(todo)}] {song.id[:8]} {song.title[:40]:<40} "
                  f"bpm={song.bpm or '-'} took {time.time()-t1:.1f}s")
            ok += 1
        except Exception as e:
            print(f"[{i}/{len(todo)}] FAIL {song.id}: {e}")
            failed += 1
            db.rollback()
    print(f"\ndone in {time.time()-t0:.1f}s — ok={ok} failed={failed}")


if __name__ == "__main__":
    main()
