#!/usr/bin/env python3
"""Generate shared instrument-analysis Shadow sidecars for the public Pilot."""
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
from app.modules.instrument_analysis.runner import InstrumentAnalysisRunner
from app.modules.instrument_analysis.service import build_instrument_analysis_document
from app.modules.instrument_analysis.store import InstrumentAnalysisStore
from app.modules.library.bar_feature_adapter import build_canonical_timeline


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_pilot_instrument_analysis(
    *,
    manifest: PilotManifest,
    db: Any,
    runner: InstrumentAnalysisRunner,
    store: InstrumentAnalysisStore,
    selected_track_ids: Optional[Sequence[str]] = None,
    overwrite: bool = False,
    fail_on_partial: bool = False,
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
        timeline = build_canonical_timeline(song)
        audio_sha = _sha256(source)
        cached = store.load(track_id)
        if (
            not overwrite
            and cached is not None
            and cached.audio_sha256 == audio_sha
            and cached.timeline_fingerprint == timeline_fingerprint(timeline)
        ):
            results.append({"track_id": track_id, "status": "cached"})
            continue
        try:
            runtime = runner.run(
                track_id=track_id,
                audio_path=source,
                stems=dict(getattr(song, "stems", None) or {}),
            )
            if runtime.audio_sha256 != audio_sha:
                raise ValueError("runtime audio fingerprint does not match the requested file")
            document = build_instrument_analysis_document(song, runtime)
            store.save(document)
            results.append(
                {
                    "track_id": track_id,
                    "status": document.status,
                    "bars": len(document.bars),
                    "warnings": document.warnings,
                }
            )
        except Exception as exc:
            results.append(
                {"track_id": track_id, "status": "failed", "error": f"{type(exc).__name__}: {exc}"[:4096]}
            )
        if fail_on_partial and results[-1]["status"] in {"partial", "failed"}:
            break

    return {
        "schema_name": "harbeat.instrument_analysis_generation_report",
        "schema_version": "0.1.0",
        "dataset_version": manifest.dataset_version,
        "selected": len(track_ids),
        "processed": len(results),
        "generated": sum(item["status"] in {"ready", "partial"} for item in results),
        "cached": sum(item["status"] == "cached" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "partial": sum(item["status"] == "partial" for item in results),
        "tracks": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--track-id", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--fail-on-partial", action="store_true")
    args = parser.parse_args()

    from app.shared.config import get_settings
    from app.shared.database import SessionLocal

    settings = get_settings()
    manifest_path = args.manifest or Path(settings.bar_annotation_pilot_manifest)
    manifest = PilotManifest.load(manifest_path)
    if not args.all and not args.track_id:
        parser.error("choose --all or at least one --track-id")
    if not settings.instrument_analysis_command:
        parser.error("INSTRUMENT_ANALYSIS_COMMAND is not configured")
    runner = InstrumentAnalysisRunner(
        command_template=settings.instrument_analysis_command,
        work_dir=settings.instrument_analysis_work_dir,
        timeout_sec=settings.instrument_analysis_timeout_sec,
    )
    store = InstrumentAnalysisStore(settings.instrument_analysis_dir)
    db = SessionLocal()
    try:
        report = generate_pilot_instrument_analysis(
            manifest=manifest,
            db=db,
            runner=runner,
            store=store,
            selected_track_ids=[] if args.all else args.track_id,
            overwrite=args.overwrite,
            fail_on_partial=args.fail_on_partial,
        )
    finally:
        db.close()
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if report["failed"] or (args.fail_on_partial and report["partial"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
