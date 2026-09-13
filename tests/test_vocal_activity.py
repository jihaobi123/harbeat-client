from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from preprocessing.publisher import _atomic_json, _sha256
from preprocessing.vocal_activity import publish_vocal_activity, sample_intervals, storage_path
from preprocessing.cli.backfill_vocal_activity import backfill


class Detector:
    provenance = {"implementation": "test", "parameters": {"threshold": 0.5}}
    calls = 0
    intervals = [{"start_ms": 100, "end_ms": 500}]

    def detect(self, path):
        self.calls += 1
        return self.intervals, 1000


def fixture(root, track_id="track-1", run_id="run-1"):
    run = root / f"published/tracks/{track_id}/runs/{run_id}"
    run.mkdir(parents=True)
    stem = run / "vocals.wav"
    sf.write(stem, np.zeros((16000, 2)), 16000)
    manifest = {"track_id": track_id, "analysis_run_id": run_id, "assets": {"stems": {
        "vocals": {"storage_key": stem.relative_to(root).as_posix(), "sha256": _sha256(stem), "duration_ms": 1000}}}}
    _atomic_json(run / "manifest.json", manifest)
    _atomic_json(run / "_SUCCESS.json", {"analysis_run_id": run_id, "manifest_sha256": _sha256(run / "manifest.json")})
    return (run / "manifest.json").relative_to(root).as_posix()


def test_sample_intervals_merge_clip_and_preserve_precision():
    assert sample_intervals([
        {"start": 1600, "end": 8000}, {"start": -100, "end": 2000},
        {"start": 9001, "end": 18000}, {"start": 10000, "end": 9000},
    ], 1000) == [{"start_ms": 0, "end_ms": 500}, {"start_ms": 563, "end_ms": 1000}]


def test_publish_idempotent_and_preserve_base(tmp_path):
    key = fixture(tmp_path)
    original = (tmp_path / key).read_bytes()
    detector = Detector()
    first = publish_vocal_activity(tmp_path, key, detector=detector)
    second = publish_vocal_activity(tmp_path, key, detector=detector)
    assert first == second and detector.calls == 1
    assert (tmp_path / key).read_bytes() == original
    data = json.loads((tmp_path / first["vocal_activity_storage_key"]).read_text())
    assert data["active_duration_ms"] == 400
    assert data["coverage_ratio"] == 0.4
    assert data["needs_review"] is True
    assert data["source"]["manifest_sha256"] == _sha256(tmp_path / key)
    detector.provenance = {"implementation": "test2"}
    newer = publish_vocal_activity(tmp_path, key, detector=detector)
    assert newer["vocal_activity_storage_key"] != first["vocal_activity_storage_key"]
    assert (tmp_path / first["vocal_activity_storage_key"]).is_file()


def test_no_voice_is_success_but_failure_is_not(tmp_path):
    key = fixture(tmp_path)
    detector = Detector()
    detector.intervals = []
    pointer = publish_vocal_activity(tmp_path, key, detector=detector)
    data = json.loads((tmp_path / pointer["vocal_activity_storage_key"]).read_text())
    assert data["status"] == "ready" and not data["has_vocals"]
    assert data["coverage_ratio"] == 0.0
    manifest = json.loads((tmp_path / key).read_text())
    (tmp_path / manifest["assets"]["stems"]["vocals"]["storage_key"]).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="SHA256"):
        publish_vocal_activity(tmp_path, key, detector=detector)


def test_corrupt_base_and_report_rejected(tmp_path):
    key = fixture(tmp_path)
    pointer = publish_vocal_activity(tmp_path, key, detector=Detector())
    report = tmp_path / pointer["vocal_activity_storage_key"]
    report.write_text("{}")
    with pytest.raises(ValueError, match="report integrity"):
        publish_vocal_activity(tmp_path, key, detector=Detector())
    (tmp_path / key).write_text((tmp_path / key).read_text() + " ")
    with pytest.raises(ValueError, match="manifest integrity"):
        publish_vocal_activity(tmp_path, key, detector=Detector())


@pytest.mark.parametrize("key", ["/etc/passwd", "../outside", "published/../../outside", ""])
def test_invalid_storage_key(tmp_path, key):
    with pytest.raises(ValueError):
        storage_path(tmp_path, key)


def test_batch_failure_visible_and_does_not_stop_other_tracks(tmp_path):
    key = fixture(tmp_path)
    index = {"items": [{"track_id": "track-1", "analysis_run_id": "run-1", "manifest_storage_key": key},
                       {"track_id": "track-2", "analysis_run_id": None, "manifest_storage_key": None}]}
    _atomic_json(tmp_path / "published/indexes/base.json", index)
    result = backfill(tmp_path, "published/indexes/base.json", "published/indexes/vocals.json", detector=Detector())
    assert result["status_summary"] == {"ready": 1, "failed": 1}
    assert result["processed_tracks"] == 2
    assert result["items"][1]["error"]
    assert json.loads((tmp_path / "published/indexes/base.json").read_text()) == index


def test_model_failure_never_publishes_success(tmp_path):
    key = fixture(tmp_path)
    class Broken(Detector):
        def detect(self, path):
            raise RuntimeError("model failed")
    with pytest.raises(RuntimeError):
        publish_vocal_activity(tmp_path, key, detector=Broken())
    assert not list((tmp_path / "published/vocal_activity").rglob("_SUCCESS.json"))


def test_export_only_bound_markers_without_audio(tmp_path):
    from preprocessing.cli.export_vocal_activity_bundle import export_bundle
    from zipfile import ZipFile
    key = fixture(tmp_path)
    _atomic_json(tmp_path / "published/indexes/base.json", {"items": [
        {"track_id": "track-1", "analysis_run_id": "run-1", "manifest_storage_key": key}]})
    backfill(tmp_path, "published/indexes/base.json", "published/indexes/vocals.json", detector=Detector())
    target = tmp_path / "vocal.zip"
    result = export_bundle(tmp_path, "published/indexes/vocals.json", target)
    assert result["tracks"] == 1
    with ZipFile(target) as bundle:
        assert "published/indexes/vocals.json" in bundle.namelist()
        assert not any(path.endswith(".wav") for path in bundle.namelist())
        assert bundle.testzip() is None
    with pytest.raises(FileExistsError):
        export_bundle(tmp_path, "published/indexes/vocals.json", target)


def test_parallel_workers_do_not_share_recurrent_model(tmp_path, monkeypatch):
    import threading
    import preprocessing.cli.backfill_vocal_activity as worker
    barrier = threading.Barrier(2)
    instances = []

    class Isolated(Detector):
        def __init__(self):
            self.owner = threading.get_ident()
            instances.append(self)

        def detect(self, path):
            assert self.owner == threading.get_ident()
            barrier.wait(timeout=5)
            return super().detect(path)

    monkeypatch.setattr(worker, "SileroDetector", Isolated)
    items = []
    for track in ("track-1", "track-2"):
        key = fixture(tmp_path, track)
        items.append({"track_id": track, "analysis_run_id": "run-1", "manifest_storage_key": key})
    _atomic_json(tmp_path / "published/indexes/base.json", {"items": items})
    result = backfill(tmp_path, "published/indexes/base.json", "published/indexes/vocals.json", workers=2)
    assert len(instances) == 2 and instances[0].owner != instances[1].owner
    assert result["status_summary"] == {"ready": 2}
