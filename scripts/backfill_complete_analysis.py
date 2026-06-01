"""Backfill complete Jetson analysis for LibrarySong rows.

Completeness here means:
- source audio exists;
- core analysis has BPM/key/beat points and status completed;
- four stem files exist and are linked in LibrarySong.stems;
- stem-derived DJ metadata is refreshed by the normal background pipeline.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from sqlalchemy import text

# Import the related mapper before LibrarySong is first inspected. The FastAPI
# app does this through app.modules.models; standalone maintenance scripts need
# to do it explicitly.
from app.modules.playlists.models import Song  # noqa: F401
from app.modules.library.background_tasks import copy_analysis_from, run_analysis_and_separation
from app.modules.library.models import LibrarySong
from app.shared.database import SessionLocal

STEMS = ("vocals", "drums", "bass", "other")


def _expected_stems(source_path: str) -> dict[str, str]:
    audio_path = Path(source_path)
    stems_dir = audio_path.parent / ".." / "stems" / "htdemucs" / audio_path.stem
    stems_dir = stems_dir.resolve()
    return {stem: str(stems_dir / f"{stem}.wav") for stem in STEMS}


def _stems_complete(row: dict) -> bool:
    stems = row.get("stems") or {}
    if not isinstance(stems, dict):
        return False
    return all(stems.get(stem) and os.path.isfile(stems[stem]) for stem in STEMS)


def _core_complete(row: dict) -> bool:
    beats = row.get("beat_points") or []
    cues = row.get("cue_points") or []
    transitions = row.get("transition_windows") or []
    return bool(row.get("bpm")) and bool(row.get("key")) and bool(beats) and bool(cues) and bool(transitions)


def _stem_analysis_complete(row: dict) -> bool:
    return bool(
        row.get("stem_activity")
        and row.get("stem_activity_windows")
        and row.get("stem_quality_profile")
    )


def _row_needs_backfill(row: dict) -> bool:
    if not row.get("source_path") or not os.path.isfile(row["source_path"]):
        return False
    return (
        row.get("analysis_status") != "completed"
        or not _core_complete(row)
        or not _stems_complete(row)
        or not _stem_analysis_complete(row)
    )


def _candidate_rows() -> list[dict]:
    db = SessionLocal()
    try:
        rows = [
            dict(row)
            for row in db.execute(
                text(
                    """
                    select id, user_id, title, artist, analysis_status, bpm, key,
                           source_path, beat_points, cue_points, transition_windows,
                           stems, stem_activity, stem_activity_windows,
                           stem_quality_profile, created_at
                    from library_songs
                    where source_path is not null and source_path <> ''
                    order by created_at
                    """
                )
            ).mappings()
        ]
        return [row for row in rows if _row_needs_backfill(row)]
    finally:
        db.close()


def _group_rows(rows: list[dict]) -> list[list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["source_path"], []).append(row)
    return list(grouped.values())


def _copy_group_from(source_id: str, target_ids: list[str]) -> int:
    if not target_ids:
        return 0
    db = SessionLocal()
    try:
        source = db.get(LibrarySong, source_id)
        if source is None:
            return 0
        copied = 0
        for target_id in target_ids:
            target = db.get(LibrarySong, target_id)
            if target is None:
                continue
            copy_analysis_from(source, target)
            db.add(target)
            copied += 1
        db.commit()
        return copied
    finally:
        db.close()


def _row_is_complete(song_id: str) -> bool:
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                select id, analysis_status, bpm, key, source_path, beat_points,
                       cue_points, transition_windows, stems, stem_activity,
                       stem_activity_windows, stem_quality_profile
                from library_songs
                where id = :id
                """
            ),
            {"id": song_id},
        ).mappings().first()
        return bool(row and not _row_needs_backfill(dict(row)))
    finally:
        db.close()


def _summarize() -> dict[str, int]:
    db = SessionLocal()
    try:
        rows = [
            dict(row)
            for row in db.execute(
                text(
                    """
                    select id, analysis_status, bpm, key, source_path, beat_points,
                           cue_points, transition_windows, stems, stem_activity,
                           stem_activity_windows, stem_quality_profile
                    from library_songs
                    where source_path is not null and source_path <> ''
                    """
                )
            ).mappings()
        ]
        missing_source = 0
        missing_core = 0
        missing_stems = 0
        missing_stem_analysis = 0
        incomplete = 0
        for row in rows:
            if not row.get("source_path") or not os.path.isfile(row["source_path"]):
                missing_source += 1
                continue
            core_ok = _core_complete(row) and row.get("analysis_status") == "completed"
            stems_ok = _stems_complete(row)
            stem_analysis_ok = _stem_analysis_complete(row)
            if not core_ok:
                missing_core += 1
            if not stems_ok:
                missing_stems += 1
            if not stem_analysis_ok:
                missing_stem_analysis += 1
            if not core_ok or not stems_ok or not stem_analysis_ok:
                incomplete += 1
        return {
            "total_with_source": len(rows),
            "missing_source": missing_source,
            "missing_core_or_status": missing_core,
            "missing_complete_stems": missing_stems,
            "missing_stem_analysis": missing_stem_analysis,
            "incomplete": incomplete,
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--skip", nargs="*", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-group-copy", action="store_true")
    args = parser.parse_args()

    rows = _candidate_rows()
    if args.only:
        only = set(args.only)
        rows = [row for row in rows if row["id"] in only]
    if args.skip:
        skip = set(args.skip)
        rows = [row for row in rows if row["id"] not in skip]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    groups = [[row] for row in rows] if args.no_group_copy else _group_rows(rows)

    print("before", _summarize(), flush=True)
    print(f"candidate_count={len(rows)} group_count={len(groups)}", flush=True)
    for idx, group in enumerate(groups, start=1):
        row = group[0]
        expected = _expected_stems(row["source_path"])
        existing_expected = all(os.path.isfile(path) for path in expected.values())
        print(
            f"[{idx}/{len(groups)}] {row['id']} user={row['user_id']} "
            f"title={row['title']} status={row['analysis_status']} "
            f"expected_stems_on_disk={existing_expected} same_source_rows={len(group)}",
            flush=True,
        )
        if args.dry_run:
            continue
        run_analysis_and_separation(row["id"])
        copied = 0
        if _row_is_complete(row["id"]):
            copied = _copy_group_from(row["id"], [item["id"] for item in group[1:]])
        print(f"[{idx}/{len(groups)}] done {row['id']} copied={copied}", flush=True)

    print("after", _summarize(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
