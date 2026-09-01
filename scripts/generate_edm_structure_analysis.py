#!/usr/bin/env python3
"""Generate shared EDMFormer Shadow sidecars for the annotation Pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.bar_annotations.pilot import PilotManifest
from app.modules.bar_annotations.service import timeline_fingerprint
from app.modules.bar_annotations.songformer_sections import SongFormerSectionStore
from app.modules.edm_structure.runner import EdmStructureRunner
from app.modules.edm_structure.service import build_edm_structure_document
from app.modules.edm_structure.store import EdmStructureStore
from app.modules.library.bar_feature_adapter import build_canonical_timeline


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_pilot_edm_structure(
    *,
    manifest: PilotManifest,
    db: Any,
    runner: EdmStructureRunner,
    store: EdmStructureStore,
    section_store: SongFormerSectionStore,
    selected_track_ids: Optional[Sequence[str]] = None,
    overwrite: bool = False,
    fail_on_failed: bool = False,
    song_model: Any = None,
) -> dict[str, Any]:
    selected = list(selected_track_ids or [])
    outside = [track_id for track_id in selected if track_id not in manifest.track_ids]
    if outside:
        raise ValueError(f"track_id is not in the Pilot manifest: {', '.join(outside)}")
    selected_set = set(selected)
    track_ids = [
        track_id
        for track_id in manifest.track_ids
        if not selected_set or track_id in selected_set
    ]
    if song_model is None:
        from app.modules import models as _all_models  # noqa: F401
        from app.modules.library.models import LibrarySong

        song_model = LibrarySong

    results: list[dict[str, Any]] = []
    for track_id in track_ids:
        song = db.get(song_model, track_id)
        source = Path(str(getattr(song, "source_path", "") or "")) if song else Path("")
        if not song or not source.is_file():
            results.append(
                {"track_id": track_id, "status": "failed", "error": "Pilot audio is missing"}
            )
            continue
        songformer = section_store.load(track_id)
        if songformer is None or songformer.status != "ready":
            results.append(
                {
                    "track_id": track_id,
                    "status": "failed",
                    "error": "A ready SongFormer sidecar is required",
                }
            )
            if fail_on_failed:
                break
            continue

        resolved_source = source.expanduser().resolve()
        audio_sha = _sha256(resolved_source)
        timeline_sha = timeline_fingerprint(build_canonical_timeline(song))
        songformer_path = section_store._path(track_id)
        songformer_sha = _sha256(songformer_path)
        cached = store.load(track_id)
        if (
            not overwrite
            and cached is not None
            and cached.status == "ready"
            and cached.audio_sha256 == audio_sha
            and cached.timeline_fingerprint == timeline_sha
            and cached.songformer_sidecar_sha256 == songformer_sha
        ):
            results.append({"track_id": track_id, "status": "cached"})
            continue
        try:
            runtime = runner.run(track_id=track_id, audio_path=resolved_source)
            if runtime.audio_sha256 != audio_sha:
                raise ValueError("runtime audio fingerprint does not match the requested file")
            document = build_edm_structure_document(
                song,
                runtime,
                songformer=songformer,
                songformer_sidecar_sha256=songformer_sha,
            )
            store.save(document)
            results.append(
                {
                    "track_id": track_id,
                    "status": document.status,
                    "segments": len(document.segments),
                    "warnings": document.warnings,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "track_id": track_id,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}"[:4096],
                }
            )
        if fail_on_failed and results[-1]["status"] == "failed":
            break

    return {
        "schema_name": "harbeat.edm_structure_generation_report",
        "schema_version": "0.1.0",
        "dataset_version": manifest.dataset_version,
        "selected": len(track_ids),
        "processed": len(results),
        "generated": sum(item["status"] == "ready" for item in results),
        "cached": sum(item["status"] == "cached" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "tracks": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--track-id", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--fail-on-failed", action="store_true")
    args = parser.parse_args()

    from app.shared.config import get_settings
    from app.shared.database import SessionLocal

    settings = get_settings()
    manifest_path = args.manifest or Path(settings.bar_annotation_pilot_manifest)
    manifest = PilotManifest.load(manifest_path)
    if not args.all and not args.track_id:
        parser.error("choose --all or at least one --track-id")
    if not settings.edm_structure_command:
        parser.error("EDM_STRUCTURE_COMMAND is not configured")
    runner = EdmStructureRunner(
        command_template=settings.edm_structure_command,
        work_dir=settings.edm_structure_work_dir,
        timeout_sec=settings.edm_structure_timeout_sec,
    )
    store = EdmStructureStore(settings.edm_structure_dir)
    section_store = SongFormerSectionStore(settings.songformer_section_dir)
    db = SessionLocal()
    try:
        report = generate_pilot_edm_structure(
            manifest=manifest,
            db=db,
            runner=runner,
            store=store,
            section_store=section_store,
            selected_track_ids=[] if args.all else args.track_id,
            overwrite=args.overwrite,
            fail_on_failed=args.fail_on_failed,
        )
    finally:
        db.close()
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
