"""Read-only handoff reference: validate pinned NAS metadata and enumerate files.

Not a web endpoint, authorization layer, or preprocessing runner. No writes.
Audio SHA256 verification is opt-in because a full library can be large.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

import jsonschema


def storage_path(root: Path, key: str) -> Path:
    if not isinstance(key, str) or not key or "\\" in key or "\x00" in key:
        raise ValueError("invalid storage_key")
    relative = PurePosixPath(key)
    if not relative.parts or relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "published":
        raise ValueError("storage_key must stay inside published/")
    path = (root / key).resolve(strict=True)
    path.relative_to((root / "published").resolve(strict=True))
    if not path.is_file():
        raise ValueError("not a regular file")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(root: Path, key: str):
    raw = storage_path(root, key).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest(), len(raw)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def enumerate_delivery(root: Path, base_index: str, vocal_index: str,
                       schema_dir: Path, *, verify_audio=False) -> dict:
    root = root.resolve(strict=True)
    base, _, _ = read_json(root, base_index)
    vocal, _, _ = read_json(root, vocal_index)
    check(len(base["items"]) == base["total_tracks"], "base index incomplete")
    check(vocal["processed_tracks"] == vocal["total_tracks"], "vocal batch incomplete")
    check(len(vocal["items"]) == vocal["total_tracks"], "vocal item count mismatch")
    check(vocal["total_tracks"] == base["total_tracks"], "base/vocal snapshot count mismatch")
    check(vocal["source_index_storage_key"] == base_index, "vocal index belongs to another snapshot")
    schemas = {}
    for name in ("same-style-track-preprocess-v1", "vocal-activity-v1"):
        schemas[name] = jsonschema.Draft202012Validator(
            json.loads((schema_dir / (name + ".schema.json")).read_text()),
            format_checker=jsonschema.FormatChecker(),
        )
    vocal_items = {}
    for item in vocal["items"]:
        identity = (item["track_id"], item["analysis_run_id"])
        check(identity not in vocal_items, "duplicate vocal binding")
        vocal_items[identity] = item
    tracks, seen = [], set()
    for item in base["items"]:
        identity = (item["track_id"], item["analysis_run_id"])
        check(identity[0] not in seen, "duplicate track")
        seen.add(identity[0])
        key = item["manifest_storage_key"]
        run_prefix = f"published/tracks/{identity[0]}/runs/{identity[1]}/"
        check(key == run_prefix + "manifest.json", "unexpected manifest location")
        manifest, manifest_hash, _ = read_json(root, key)
        schemas["same-style-track-preprocess-v1"].validate(manifest)
        check((manifest["track_id"], manifest["analysis_run_id"]) == identity, "base identity mismatch")
        check(manifest["status"] != "unavailable", "base result unavailable")
        marker_key = run_prefix + "_SUCCESS.json"
        marker, _, _ = read_json(root, marker_key)
        check(marker["analysis_run_id"] == identity[1] and marker["manifest_sha256"] == manifest_hash,
              "base completion marker mismatch")
        if item.get("manifest_sha256"):
            check(item["manifest_sha256"] == manifest_hash, "index manifest hash mismatch")
        assets = [("master", manifest["assets"]["master"])]
        assets += [("stems." + k, manifest["assets"]["stems"][k]) for k in ("vocals", "drums", "bass", "other")]
        assets += [("drums." + k, manifest["assets"]["drum_stems"][k]) for k in ("kick", "snare", "hihat", "tom", "cymbal")]
        check(marker["asset_count"] == 10, "full handoff requires 10 audio assets")
        files = []
        for role, asset in assets:
            check(isinstance(asset, dict), "required audio missing: " + role)
            check(asset["storage_key"].startswith(run_prefix + "audio/"), "audio belongs to another run")
            path = storage_path(root, asset["storage_key"])
            check(path.stat().st_size == asset["size_bytes"], "audio size mismatch: " + role)
            if verify_audio:
                check(sha256_file(path) == asset["sha256"], "audio SHA256 mismatch: " + role)
            files.append({"role": role, **asset})
        check(identity in vocal_items, "missing vocal binding for base run")
        pointer = vocal_items[identity]
        check(pointer["status"] == "ready", "vocal result not ready")
        report_key = pointer["vocal_activity_storage_key"]
        check(report_key.startswith(f"published/vocal_activity/{identity[0]}/{identity[1]}/"), "vocal path mismatch")
        report, report_hash, _ = read_json(root, report_key)
        schemas["vocal-activity-v1"].validate(report)
        check(report["status"] == "ready", "vocal report failed")
        check(report_hash == pointer["vocal_activity_sha256"], "vocal SHA256 mismatch")
        expected = {"track_id": identity[0], "analysis_run_id": identity[1],
                    "manifest_storage_key": key, "manifest_sha256": manifest_hash,
                    "vocal_storage_key": manifest["assets"]["stems"]["vocals"]["storage_key"],
                    "vocal_sha256": manifest["assets"]["stems"]["vocals"]["sha256"]}
        check(report["source"] == expected, "vocal input binding mismatch")
        check(all(pointer[k] == v for k, v in expected.items()), "vocal index binding mismatch")
        vocal_marker_key = str(PurePosixPath(report_key).parent / "_SUCCESS.json")
        vocal_marker, _, _ = read_json(root, vocal_marker_key)
        check(vocal_marker["vocal_activity_sha256"] == report_hash, "vocal completion marker mismatch")
        previous_end, active = 0, 0
        for span in report["intervals"]:
            start, end = span["start_ms"], span["end_ms"]
            check(previous_end <= start < end <= report["duration_ms"], "invalid vocal timeline")
            previous_end, active = end, active + end - start
        check(active == report["active_duration_ms"], "vocal active duration mismatch")
        check(bool(report["intervals"]) == report["has_vocals"], "vocal presence mismatch")
        check(abs(active / report["duration_ms"] - report["coverage_ratio"]) < 1e-8, "vocal coverage mismatch")
        check(abs(report["duration_ms"] - manifest["assets"]["stems"]["vocals"]["duration_ms"]) <= 100,
              "vocal time axis mismatch")
        for role, metadata_key in (("manifest", key), ("base_success", marker_key),
                                   ("vocal_activity", report_key), ("vocal_success", vocal_marker_key)):
            _, digest, size = read_json(root, metadata_key)
            files.append({"role": role, "storage_key": metadata_key, "sha256": digest,
                          "size_bytes": size, "content_type": "application/json"})
        check(len({f["storage_key"] for f in files}) == len(files), "duplicate file location")
        tracks.append({"track_id": identity[0], "analysis_run_id": identity[1],
                       "manifest_storage_key": key, "manifest_sha256": manifest_hash,
                       "title": manifest["source"]["title"], "style_labels": manifest["source"]["style_labels"],
                       "duration_ms": manifest["source"]["duration_ms"], "status": manifest["status"],
                       "quality": manifest["quality"], "analysis": manifest["analysis"],
                       "vocal_activity_sha256": report_hash, "files": files})
    return {"schema_name": "harbeat_backend_reference_inventory", "schema_version": "0.1.0",
            "purpose": "read-only development reference, not an authorized download response",
            "audio_hashes_verified": verify_audio, "total_tracks": len(tracks),
            "total_files": sum(len(t["files"]) for t in tracks),
            "total_bytes": sum(f["size_bytes"] for t in tracks for f in t["files"]), "tracks": tracks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--base-index", default="published/indexes/edm_8_handoff_v1.json")
    parser.add_argument("--vocal-index", default="published/indexes/edm_8_vocal_activity_v1.json")
    parser.add_argument("--schema-dir", type=Path,
                        default=Path(__file__).resolve().parents[3] / "contracts/schemas/analysis")
    parser.add_argument("--verify-audio", action="store_true")
    args = parser.parse_args()
    print(json.dumps(enumerate_delivery(args.root, args.base_index, args.vocal_index,
                                       args.schema_dir, verify_audio=args.verify_audio), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
