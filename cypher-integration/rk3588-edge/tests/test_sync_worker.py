import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC_MAIN = ROOT / "sync-worker" / "main.py"


def _load_sync_worker():
    spec = importlib.util.spec_from_file_location("sync_worker_main", SYNC_MAIN)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_manifest_file_items_expand_original_and_four_stems_in_order():
    sync_worker = _load_sync_worker()
    manifest = {
        "plan_id": "plan-1",
        "tracks": [
            {
                "song_id": "song-a",
                "files": {
                    "original": {"url": "/stream/song-a/original.wav", "size": 10},
                    "stems": {
                        "vocals": {"url": "/stream/song-a/vocals.wav"},
                        "drums": {"url": "/stream/song-a/drums.wav"},
                        "bass": {"url": "/stream/song-a/bass.wav"},
                        "other": {"url": "/stream/song-a/other.wav"},
                    },
                },
            }
        ],
    }

    items = sync_worker._file_items(manifest)

    assert [(item["song_id"], item["kind"]) for item in items] == [
        ("song-a", "original"),
        ("song-a", "vocals"),
        ("song-a", "drums"),
        ("song-a", "bass"),
        ("song-a", "other"),
    ]


def test_status_reports_missing_required_stems_before_download():
    sync_worker = _load_sync_worker()
    manifest = {
        "tracks": [
            {
                "id": "song-b",
                "files": {
                    "original": {"url": "/stream/song-b/original.wav"},
                    "stems": {"vocals": {"url": "/stream/song-b/vocals.wav"}},
                },
            }
        ]
    }

    report = sync_worker._manifest_asset_report(manifest)

    assert report["track_count"] == 1
    assert report["asset_count"] == 2
    assert report["complete_tracks"] == 0
    assert report["missing"]["song-b"] == ["drums", "bass", "other"]
