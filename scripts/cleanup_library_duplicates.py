"""Clean duplicate rows in library_songs and install dedupe indexes.

The cleanup is intentionally conservative:
- scope is per user only;
- duplicates are rows with the same non-empty source_path, or the same non-empty
  platform_id;
- shared audio files are not deleted.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from app.shared.database import SessionLocal


@dataclass
class Candidate:
    row: dict
    cached: bool

    @property
    def id(self) -> str:
        return str(self.row["id"])

    def score(self) -> tuple:
        status = str(self.row.get("analysis_status") or "")
        completed = 1 if status == "completed" else 0
        has_stems = 1 if self.row.get("has_stems") else 0
        has_beats = 1 if self.row.get("has_beats") else 0
        updated = self.row.get("updated_at") or datetime.min
        created = self.row.get("created_at") or datetime.min
        return (completed, has_stems, has_beats, int(self.cached), updated, created)


def _cache_ids(cache_dir: str | None) -> set[str]:
    explicit = {
        item.strip()
        for item in os.environ.get("RK_CACHED_IDS", "").split(",")
        if item.strip()
    }
    if not cache_dir:
        return explicit
    root = Path(cache_dir)
    if not root.is_dir():
        return explicit
    return explicit | {p.name for p in root.iterdir() if p.is_dir()}


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _duplicate_rows(db) -> list[dict]:
    sql = text(
        """
        with dup_keys as (
            select user_id, source_path as key
            from library_songs
            where source_path is not null and trim(source_path) <> ''
            group by user_id, source_path having count(*) > 1
            union
            select user_id, platform_id as key
            from library_songs
            where platform_id is not null and trim(platform_id) <> ''
            group by user_id, platform_id having count(*) > 1
        )
        select ls.*,
               case when coalesce(ls.beat_points::text, '[]') not in ('[]','null') then 1 else 0 end as has_beats,
               case when coalesce(ls.stems::text, 'null') not in ('null','{}') then 1 else 0 end as has_stems
        from library_songs ls
        where exists (
            select 1 from dup_keys d
            where d.user_id = ls.user_id
              and (d.key = ls.source_path or d.key = ls.platform_id)
        )
        order by ls.user_id, coalesce(ls.source_path, ls.platform_id), ls.created_at
        """
    )
    return [dict(row) for row in db.execute(sql).mappings().all()]


def _plan(rows: list[dict], cached_ids: set[str]) -> tuple[list[dict], list[str]]:
    groups: dict[tuple, list[Candidate]] = {}
    for row in rows:
        keys = []
        source_path = (row.get("source_path") or "").strip()
        platform_id = (row.get("platform_id") or "").strip()
        if source_path:
            keys.append(("source_path", row["user_id"], source_path))
        if platform_id:
            keys.append(("platform_id", row["user_id"], platform_id))
        for key in keys:
            groups.setdefault(key, []).append(Candidate(row=row, cached=row["id"] in cached_ids))

    keep_ids: set[str] = set()
    delete_ids: set[str] = set()
    decisions: list[dict] = []

    seen_decisions: set[tuple[str, tuple[str, ...]]] = set()

    for key, candidates in sorted(groups.items()):
        unique = {c.id: c for c in candidates}
        if len(unique) <= 1:
            continue
        canonical_candidates = list(unique.values())
        keeper = max(canonical_candidates, key=lambda c: c.score())
        deletes = tuple(sorted(c.id for c in canonical_candidates if c.id != keeper.id))
        decision_key = (keeper.id, deletes)
        if decision_key in seen_decisions:
            continue
        seen_decisions.add(decision_key)
        keep_ids.add(keeper.id)
        for candidate_id in deletes:
            delete_ids.add(candidate_id)
        decisions.append(
            {
                "key": key,
                "keep": keeper.id,
                "delete": list(deletes),
                "title": keeper.row.get("title"),
                "artist": keeper.row.get("artist"),
            }
        )

    delete_ids -= keep_ids
    return decisions, sorted(delete_ids)


def _install_indexes(db) -> None:
    db.execute(
        text(
            """
            create unique index if not exists uq_library_songs_user_platform_id_dedup
            on library_songs (user_id, platform_id)
            where platform_id is not null and btrim(platform_id) <> ''
            """
        )
    )
    db.execute(
        text(
            """
            create unique index if not exists uq_library_songs_user_source_path_dedup
            on library_songs (user_id, source_path)
            where source_path is not null and btrim(source_path) <> ''
            """
        )
    )
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="delete duplicate rows and install indexes")
    parser.add_argument("--cache-dir", default=os.environ.get("RK_CACHE_DIR", ""))
    parser.add_argument("--backup-json", default="")
    args = parser.parse_args()

    cached_ids = _cache_ids(args.cache_dir)
    db = SessionLocal()
    try:
        rows = _duplicate_rows(db)
        decisions, delete_ids = _plan(rows, cached_ids)
        print(f"duplicate_groups={len(decisions)} delete_rows={len(delete_ids)}")
        for item in decisions:
            print(
                f"keep={item['keep']} delete={','.join(item['delete'])} "
                f"title={item['title']} artist={item['artist']}"
            )

        if not args.apply:
            print("dry_run=true")
            return 0

        backup_path = args.backup_json or f"/tmp/library_songs_duplicate_backup_{datetime.utcnow():%Y%m%d_%H%M%S}.json"
        Path(backup_path).write_text(json.dumps(rows, ensure_ascii=False, default=_json_default, indent=2), encoding="utf-8")
        print(f"backup_json={backup_path}")

        if delete_ids:
            db.execute(
                text("delete from library_songs where id = any(:ids)"),
                {"ids": delete_ids},
            )
            db.commit()

        _install_indexes(db)
        print("applied=true")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
