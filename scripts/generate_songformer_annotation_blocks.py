#!/usr/bin/env python3
"""Generate shared SongFormer section sidecars for the public Pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.bar_annotations.pilot import PilotManifest
from app.modules.bar_annotations.songformer_sections import (
    SongFormerRunner,
    SongFormerSectionStore,
)


def generate_pilot_sections(
    *,
    manifest: PilotManifest,
    db: Any,
    runner: SongFormerRunner,
    selected_track_ids: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    force: bool = False,
    stop_on_error: bool = False,
    song_model: Any = None,
) -> dict[str, Any]:
    """Process only manifest tracks, preserving manifest order."""

    selected = list(selected_track_ids or [])
    outside_manifest = [track_id for track_id in selected if track_id not in manifest.track_ids]
    if outside_manifest:
        raise ValueError(
            f"track_id is not in the Pilot manifest: {', '.join(outside_manifest)}"
        )
    selected_set = set(selected)
    track_ids = [
        track_id
        for track_id in manifest.track_ids
        if not selected_set or track_id in selected_set
    ]

    if song_model is None:
        from app.modules.library.models import LibrarySong

        song_model = LibrarySong

    results: list[dict[str, Any]] = []
    for track_id in track_ids:
        song = db.get(song_model, track_id)
        source_path = str(getattr(song, "source_path", "") or "") if song else ""
        if dry_run:
            results.append(
                {
                    "track_id": track_id,
                    "source_path": source_path,
                    "status": "dry_run",
                }
            )
            continue
        if not song or not source_path or not Path(source_path).is_file():
            results.append(
                {
                    "track_id": track_id,
                    "source_path": source_path,
                    "status": "failed",
                    "error": "Pilot song or source audio is missing",
                }
            )
        else:
            document = runner.run(
                track_id=track_id,
                audio_path=source_path,
                force=force,
            )
            results.append(
                {
                    "track_id": track_id,
                    "source_path": source_path,
                    "status": document.status,
                    "segments": len(document.segments),
                    "error": document.error,
                }
            )
        if stop_on_error and results[-1]["status"] == "failed":
            break

    return {
        "schema_name": "harbeat.songformer_pilot_generation_report",
        "schema_version": "1.0.0",
        "dataset_version": manifest.dataset_version,
        "selected": len(track_ids),
        "processed": len(results),
        "ready": sum(item["status"] == "ready" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "dry_run": sum(item["status"] == "dry_run" for item in results),
        "tracks": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate SongFormer annotation blocks without changing human labels"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--track-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    from app.shared.config import get_settings
    from app.shared.database import SessionLocal

    settings = get_settings()
    if not settings.songformer_command and not args.dry_run:
        parser.error("SONGFORMER_COMMAND is not configured")
    manifest = PilotManifest.load(args.manifest)
    runner = SongFormerRunner(
        command_template=settings.songformer_command,
        work_dir=settings.songformer_work_dir,
        timeout_sec=settings.songformer_timeout_sec,
        store=SongFormerSectionStore(settings.songformer_section_dir),
    )
    db = SessionLocal()
    try:
        summary = generate_pilot_sections(
            manifest=manifest,
            db=db,
            runner=runner,
            selected_track_ids=args.track_id,
            dry_run=args.dry_run,
            force=args.force,
            stop_on_error=args.stop_on_error,
        )
    finally:
        db.close()

    for result in summary["tracks"]:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print(json.dumps({key: value for key, value in summary.items() if key != "tracks"}, sort_keys=True))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
