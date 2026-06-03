#!/usr/bin/env python
"""Backfill external style evidence for library songs.

Examples:
  python scripts/backfill_style_evidence.py --limit 50
  python scripts/backfill_style_evidence.py --force --user-id 1
  python scripts/backfill_style_evidence.py --only-missing
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.playlists import models as _playlist_models  # noqa: F401 - registers Song relationship
from app.modules.library.external_metadata import run_enrich_song_external_metadata
from app.modules.library.models import LibrarySong
from app.shared.database import SessionLocal


def _has_style_evidence(song: LibrarySong) -> bool:
    gp = song.genre_profile or {}
    return bool(isinstance(gp, dict) and gp.get("style_evidence_v1"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--user-id", type=int)
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        q = db.query(LibrarySong).order_by(LibrarySong.created_at.asc())
        if args.user_id is not None:
            q = q.filter(LibrarySong.user_id == args.user_id)
        songs = q.all()
        processed = 0
        for song in songs:
            if args.only_missing and _has_style_evidence(song) and not args.force:
                continue
            if processed >= max(0, args.limit):
                break
            result = run_enrich_song_external_metadata(db, song, force=args.force)
            best_style = max(result.dance_style_scores.items(), key=lambda kv: kv[1])[0] if result.dance_style_scores else "-"
            best_score = result.dance_style_scores.get(best_style, 0.0) if best_style != "-" else 0.0
            statuses = ",".join(f"{k}:{v}" for k, v in result.source_statuses().items())
            print(
                f"{song.id}\t{song.title}\t{best_style}:{best_score:.3f}\t{result.status}\t{statuses}",
                flush=True,
            )
            processed += 1
        print(f"processed={processed}", flush=True)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
