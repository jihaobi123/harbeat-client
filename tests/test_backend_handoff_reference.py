"""Offline tests for the backend handoff reader; never invoke models or services."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("read_delivery", ROOT / "docs/backend-v2/reference/read_delivery.py")
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)
BASE = "published/indexes/edm_8_handoff_v1.json"
VOCAL = "published/indexes/edm_8_vocal_activity_v1.json"
SCHEMAS = ROOT / "contracts/schemas/analysis"


def write_json(root, key, data):
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def bundle(tmp_path):
    m = json.loads((ROOT / "contracts/fixtures/analysis/same-style-track-preprocess-v1.ready.json").read_text())
    track, run = m["track_id"], m["analysis_run_id"]
    prefix = f"published/tracks/{track}/runs/{run}/"
    assets = [m["assets"]["master"], *m["assets"]["stems"].values()]
    assets += [m["assets"]["drum_stems"][k] for k in ("kick", "snare", "hihat", "tom", "cymbal")]
    for i, asset in enumerate(assets):
        data = f"fake-audio-{i:02}".encode()
        asset["storage_key"] = prefix + f"audio/fixture-{i}.wav"
        asset["size_bytes"] = len(data)
        asset["sha256"] = hashlib.sha256(data).hexdigest()
        path = tmp_path / asset["storage_key"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    key = prefix + "manifest.json"
    mh = write_json(tmp_path, key, m)
    write_json(tmp_path, prefix + "_SUCCESS.json", {"analysis_run_id":run,"manifest_sha256":mh,"asset_count":10})
    base = {"total_tracks":1,"items":[{"track_id":track,"analysis_run_id":run,"manifest_storage_key":key}]}
    write_json(tmp_path, BASE, base)
    binding = {"track_id":track,"analysis_run_id":run,"manifest_storage_key":key,"manifest_sha256":mh,
               "vocal_storage_key":m["assets"]["stems"]["vocals"]["storage_key"],
               "vocal_sha256":m["assets"]["stems"]["vocals"]["sha256"]}
    report = {"schema_name":"harbeat_vocal_activity","schema_version":"1.0.0","status":"ready",
              "generated_at":"2026-09-13T00:00:00Z","source":binding,
              "producer":{"implementation":"silero_vocal_activity_v1","model":"silero_vad",
                          "package_version":"test","model_sha256":"0"*64,"backend":"torchscript_cpu",
                          "torch_version":"test","parameters":{"threshold":0.5,"neg_threshold":0.35,
                          "min_speech_duration_ms":250,"min_silence_duration_ms":300,"speech_pad_ms":100,
                          "sampling_rate":16000},"resampling":"scipy.signal.resample_poly","channel_reduction":"arithmetic_mean"},
              "unit":"ms","time_origin":"master_audio_start","interval_convention":"[start_ms,end_ms)",
              "duration_ms":m["assets"]["stems"]["vocals"]["duration_ms"],"intervals":[],"has_vocals":False,
              "active_duration_ms":0,"coverage_ratio":0.0,"needs_review":True,"quality_flags":[]}
    vk = f"published/vocal_activity/{track}/{run}/fixture/vocal_activity.json"
    vh = write_json(tmp_path, vk, report)
    write_json(tmp_path, str(Path(vk).parent / "_SUCCESS.json"), {"vocal_activity_sha256":vh})
    vi = {**binding,"status":"ready","vocal_activity_storage_key":vk,"vocal_activity_sha256":vh}
    write_json(tmp_path, VOCAL, {"total_tracks":1,"processed_tracks":1,"source_index_storage_key":BASE,"items":[vi]})
    return tmp_path, m, key, vk


def read(bundle, **kwargs):
    return reader.enumerate_delivery(bundle[0], BASE, VOCAL, SCHEMAS, **kwargs)


def test_full_bundle_and_no_writes(bundle):
    root = bundle[0]
    before = {str(p):p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = read(bundle, verify_audio=True)
    assert result["total_tracks"] == 1 and result["total_files"] == 14
    assert result["audio_hashes_verified"] is True
    assert before == {str(p):p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_pinned_snapshot_does_not_follow_latest(bundle):
    root, m, _, _ = bundle
    write_json(root, f"published/tracks/{m['track_id']}/latest.json", {"analysis_run_id":"different"})
    assert read(bundle)["tracks"][0]["analysis_run_id"] == m["analysis_run_id"]


def test_audio_hash_mode_is_explicit(bundle):
    root, m, _, _ = bundle
    p = root / m["assets"]["master"]["storage_key"]
    p.write_bytes(b"x" * p.stat().st_size)
    assert read(bundle)["audio_hashes_verified"] is False
    with pytest.raises(ValueError, match="audio SHA256"):
        read(bundle, verify_audio=True)


def test_corrupt_manifest_rejected(bundle):
    (bundle[0] / bundle[2]).write_text((bundle[0] / bundle[2]).read_text()+" ")
    with pytest.raises(ValueError, match="completion marker"):
        read(bundle)


def test_wrong_vocal_binding_rejected(bundle):
    root, _, _, vk = bundle
    data = json.loads((root / VOCAL).read_text())
    data["items"][0]["manifest_sha256"] = "f"*64
    write_json(root, VOCAL, data)
    with pytest.raises(ValueError, match="vocal index binding"):
        read(bundle)


def test_missing_audio_rejected(bundle):
    (bundle[0] / bundle[1]["assets"]["drum_stems"]["kick"]["storage_key"]).unlink()
    with pytest.raises(FileNotFoundError):
        read(bundle)


@pytest.mark.parametrize("key", ["/etc/passwd","published/../../etc/passwd","published\\escape","staging/x", "", ".", "published/\x00bad"])
def test_path_escape_rejected(bundle, key):
    with pytest.raises(ValueError):
        reader.storage_path(bundle[0], key)


def test_symlink_escape_rejected(bundle, tmp_path):
    link = tmp_path / "published/escape"
    link.symlink_to(ROOT / "README.md")
    with pytest.raises(ValueError):
        reader.storage_path(tmp_path,"published/escape")


def test_missing_vocal_binding_rejected(bundle):
    data = json.loads((bundle[0] / VOCAL).read_text())
    data["items"][0]["analysis_run_id"] = "another-run"
    write_json(bundle[0], VOCAL, data)
    with pytest.raises(ValueError, match="missing vocal binding"):
        read(bundle)


def test_different_snapshot_counts_rejected(bundle):
    data = json.loads((bundle[0] / VOCAL).read_text())
    data.update(items=[], total_tracks=0, processed_tracks=0)
    write_json(bundle[0], VOCAL, data)
    with pytest.raises(ValueError, match="snapshot count mismatch"):
        read(bundle)


def test_handoff_navigation_exists():
    for source in (ROOT / "docs/backend-v2").glob("*.md"):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", source.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            assert (source.parent / target.split("#",1)[0]).exists(), (source, target)
