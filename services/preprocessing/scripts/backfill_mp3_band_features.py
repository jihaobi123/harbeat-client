"""Backfill MP3 low/mid/high band ratios into LibrarySong.music_features['dj']."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def backfill_mp3_band_features(*, limit: int | None = None, force: bool = False, dry_run: bool = False) -> int:
    from app.modules.dj_control.auto_mixer.feature_analyzer import FeatureAnalyzer
    from app.modules.library.models import LibrarySong
    from app.modules.playlists import models as _playlist_models  # noqa: F401
    from app.shared.database import SessionLocal

    db = SessionLocal()
    success = 0
    failed = 0
    try:
        query = db.query(LibrarySong).filter(LibrarySong.source_path != "")
        songs = query.all()
        if limit:
            songs = songs[:limit]

        for index, song in enumerate(songs, 1):
            source_path = getattr(song, "source_path", "") or ""
            music_features = dict(getattr(song, "music_features", None) or {})
            dj = dict(music_features.get("dj") or {})
            already = all(key in dj for key in ("low_ratio", "mid_ratio", "high_ratio"))
            if already and not force:
                continue
            print(f"[{index}/{len(songs)}] {song.id} {song.title}", flush=True)
            if not source_path or not os.path.isfile(source_path):
                print(f"  missing source_path: {source_path}", flush=True)
                failed += 1
                continue
            try:
                features = FeatureAnalyzer.extract_features(
                    source_path,
                    {"bpm": song.bpm, "energy": song.energy},
                )
                dj.update(features)
                dj["band_feature_source"] = "mp3_spectrum"
                music_features["dj"] = dj
                if dry_run:
                    print(f"  dry-run {features}", flush=True)
                else:
                    song.music_features = music_features
                    db.add(song)
                    db.commit()
                    print(
                        "  written "
                        f"low={features['low_ratio']:.3f} "
                        f"mid={features['mid_ratio']:.3f} "
                        f"high={features['high_ratio']:.3f}",
                        flush=True,
                    )
                success += 1
            except Exception as exc:
                db.rollback()
                failed += 1
                print(f"  failed: {exc}", flush=True)
        print(f"done success={success} failed={failed}", flush=True)
        return 0 if failed == 0 else 1
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return backfill_mp3_band_features(limit=args.limit, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
