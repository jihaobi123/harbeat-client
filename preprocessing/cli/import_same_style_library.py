#!/usr/bin/env python3
"""Safely import labelled ZIP libraries and publish resumable track analyses.

The immediate parent directory of each audio file is treated as its
human-authored style label. Identical audio found in more than one archive is
deduplicated by SHA256 and keeps the union of its labels.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from typing import Any
import unicodedata
from zipfile import ZipFile, ZipInfo


AUDIO_SUFFIXES = {".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".wma"}
CATALOG_SCHEMA_VERSION = "1.0.0"
_DOWNLOAD_SUFFIX = re.compile(r"\.\d{10,}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decoded_name(info: ZipInfo) -> str:
    """Repair UTF-8 names saved without the ZIP UTF-8 flag."""
    name = info.filename
    if info.flag_bits & 0x800:
        return unicodedata.normalize("NFC", name)
    try:
        name = name.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return unicodedata.normalize("NFC", name)


def _safe_parts(name: str) -> tuple[str, ...]:
    candidate = PurePosixPath(name.replace("\\", "/"))
    parts = tuple(part for part in candidate.parts if part not in ("", "."))
    if candidate.is_absolute() or not parts or ".." in parts:
        raise ValueError(f"unsafe ZIP member path: {name!r}")
    return parts


def _is_ignored(parts: tuple[str, ...]) -> bool:
    return "__MACOSX" in parts or parts[-1] == ".DS_Store" or parts[-1].startswith("._")


def _is_symlink(info: ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def extract_archive(archive: Path, destination: Path) -> list[Path]:
    """Extract audio only, rejecting links/traversal and repairing filenames."""
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with ZipFile(archive) as handle:
        for info in handle.infolist():
            parts = _safe_parts(_decoded_name(info))
            if _is_ignored(parts) or info.is_dir():
                continue
            if _is_symlink(info):
                raise ValueError(f"symbolic link is not accepted: {info.filename!r}")
            if Path(parts[-1]).suffix.lower() not in AUDIO_SUFFIXES:
                continue
            target = destination.joinpath(*parts).resolve()
            try:
                target.relative_to(destination.resolve())
            except ValueError as exc:
                raise ValueError(f"unsafe extracted path: {target}") from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file() or target.stat().st_size != info.file_size:
                temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
                with handle.open(info) as source, temporary.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, target)
            extracted.append(target)
    return extracted


def _clean_stem(path: Path) -> str:
    return _DOWNLOAD_SUFFIX.sub("", path.stem).strip()


def _title_artist(path: Path, collection: str) -> tuple[str, str | None]:
    stem = _clean_stem(path)
    if " - " not in stem:
        return stem, None
    left, right = (value.strip() for value in stem.split(" - ", 1))
    if collection.casefold() == "kpop":
        return left, right or None
    return right or stem, left or None


def _relative_storage_key(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def build_inventory(archives: list[Path], import_root: Path) -> list[dict[str, Any]]:
    by_hash: dict[str, dict[str, Any]] = {}
    extracted_root = import_root / "extracted"
    for archive in archives:
        collection = archive.stem
        paths = extract_archive(archive, extracted_root / collection)
        for path in paths:
            digest = _sha256(path)
            style = path.parent.name.strip()
            item = by_hash.setdefault(
                digest,
                {
                    "track_id": f"track-{digest[:20]}",
                    "input_sha256": digest,
                    "original_filename": path.name,
                    "source_path": str(path.resolve()),
                    "source_storage_key": _relative_storage_key(import_root, path),
                    "source_collection": collection,
                    "collection_labels": [],
                    "style_labels": [],
                    "duplicate_sources": [],
                    "status": "pending",
                    "analysis_run_id": None,
                    "manifest_storage_key": None,
                    "error": None,
                },
            )
            if collection not in item["collection_labels"]:
                item["collection_labels"].append(collection)
            if style and style not in item["style_labels"]:
                item["style_labels"].append(style)
            source_key = _relative_storage_key(import_root, path)
            if source_key != item["source_storage_key"] and source_key not in item["duplicate_sources"]:
                item["duplicate_sources"].append(source_key)
    for item in by_hash.values():
        title, artist = _title_artist(Path(item["source_path"]), item["source_collection"])
        item["title"] = title
        item["artist"] = artist
        item["collection_labels"].sort(key=str.casefold)
        item["style_labels"].sort(key=str.casefold)
        item["duplicate_sources"].sort(key=str.casefold)
    return sorted(by_hash.values(), key=lambda value: (value["style_labels"], value["original_filename"].casefold()))


def _catalog(items: list[dict[str, Any]], collections: list[str]) -> dict[str, Any]:
    counts = Counter(str(item["status"]) for item in items)
    public_items = []
    for item in items:
        public_items.append({key: value for key, value in item.items() if key != "source_path"})
    return {
        "schema_name": "same_style_library_index",
        "schema_version": CATALOG_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "source_collections": collections,
        "total_tracks": len(items),
        "status_summary": dict(sorted(counts.items())),
        "items": public_items,
    }


def _write_catalog(items: list[dict[str, Any]], collections: list[str], import_root: Path, preprocess_root: Path) -> None:
    payload = _catalog(items, collections)
    try:
        import jsonschema

        schema_path = Path(__file__).resolve().parents[2] / "contracts" / "schemas" / "analysis" / "same-style-library-index-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(payload)
    except ImportError as exc:
        raise RuntimeError("jsonschema is required by the library importer") from exc
    _atomic_json(import_root / "state" / "library.json", payload)
    _atomic_json(preprocess_root / "published" / "indexes" / "style_library_v1.json", payload)


def _analyze(item: dict[str, Any], args: argparse.Namespace) -> None:
    command = [
        str(args.command),
        item["source_path"],
        "--root",
        str(args.preprocess_root),
        "--track-id",
        item["track_id"],
        "--title",
        item["title"],
        "--disable-adtof",
    ]
    if item.get("artist"):
        command.extend(["--artist", item["artist"]])
    for label in item["style_labels"]:
        command.extend(["--style-label", label])
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-4000:]
        raise RuntimeError(f"preprocess exited {completed.returncode}: {detail}")
    lines = [line for line in completed.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        raise RuntimeError("preprocess command returned no JSON result")
    result = json.loads(lines[-1])
    item["status"] = result["status"]
    item["analysis_run_id"] = result["analysis_run_id"]
    latest = args.preprocess_root / "published" / "tracks" / item["track_id"] / "latest.json"
    pointer = json.loads(latest.read_text(encoding="utf-8"))
    item["manifest_storage_key"] = pointer["manifest_storage_key"]
    item["error"] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--import-root", required=True, type=Path)
    parser.add_argument("--preprocess-root", required=True, type=Path)
    parser.add_argument("--command", type=Path, default=Path("/usr/local/bin/harbeat-same-style-preprocess"))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.import_root = args.import_root.expanduser().resolve()
    args.preprocess_root = args.preprocess_root.expanduser().resolve()
    archives = [path.expanduser().resolve() for path in args.archives]
    missing = [str(path) for path in archives if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"archives not found: {missing}")
    collections = [path.stem for path in archives]
    state_path = args.import_root / "state" / "library.json"
    inventory = build_inventory(archives, args.import_root)
    if state_path.is_file():
        previous = json.loads(state_path.read_text(encoding="utf-8"))
        previous_by_id = {item["track_id"]: item for item in previous.get("items", [])}
        for item in inventory:
            old = previous_by_id.get(item["track_id"])
            metadata_matches = bool(
                old
                and old.get("input_sha256") == item["input_sha256"]
                and old.get("style_labels") == item["style_labels"]
                and old.get("title") == item["title"]
                and old.get("artist") == item["artist"]
            )
            if metadata_matches:
                for key in ("status", "analysis_run_id", "manifest_storage_key", "error"):
                    item[key] = old.get(key)
                if item["status"] == "running":
                    item["status"] = "pending"
                    item["error"] = "previous worker stopped while this track was running"
    _write_catalog(inventory, collections, args.import_root, args.preprocess_root)
    if args.prepare_only:
        print(json.dumps(_catalog(inventory, collections), ensure_ascii=False))
        return 0

    selected = [
        item for item in inventory
        if item["status"] == "pending" or (args.retry_failed and item["status"] == "failed")
    ]
    if args.limit is not None:
        selected = selected[: max(0, args.limit)]
    for index, item in enumerate(selected, 1):
        item["status"] = "running"
        item["error"] = None
        _write_catalog(inventory, collections, args.import_root, args.preprocess_root)
        print(f"[{index}/{len(selected)}] {item['track_id']} {item['style_labels']} {item['original_filename']}", flush=True)
        try:
            _analyze(item, args)
        except Exception as exc:
            item["status"] = "failed"
            item["error"] = f"{type(exc).__name__}: {str(exc)[:2000]}"
            print(item["error"], file=sys.stderr, flush=True)
        _write_catalog(inventory, collections, args.import_root, args.preprocess_root)
    print(json.dumps(_catalog(inventory, collections), ensure_ascii=False))
    return 0 if not any(item["status"] == "failed" for item in inventory) else 2


if __name__ == "__main__":
    raise SystemExit(main())
