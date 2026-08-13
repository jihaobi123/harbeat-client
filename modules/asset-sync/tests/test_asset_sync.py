import asyncio
import importlib
import json
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load():
    if "fastapi" not in sys.modules:
        try:
            __import__("fastapi")
        except ModuleNotFoundError:
            stub = types.ModuleType("fastapi")

            class FastAPI:
                def __init__(self, *args, **kwargs):
                    pass

                def post(self, *args, **kwargs):
                    return lambda fn: fn

                def get(self, *args, **kwargs):
                    return lambda fn: fn

                def delete(self, *args, **kwargs):
                    return lambda fn: fn

            stub.FastAPI = FastAPI
            sys.modules["fastapi"] = stub
    import harbeat_asset_sync.sync_worker as module
    return importlib.reload(module)


def test_manifest_expands_songs_stems_and_pair_files():
    sync = _load()
    manifest = {
        "tracks": [{
            "song_id": "song-a",
            "files": {
                "original": {"url": "/original.wav"},
                "stems": {key: {"url": f"/{key}.wav"} for key in ("vocals", "drums", "bass", "other")},
            },
        }],
        "default_mix_pairs": [{
            "pair_id": "pair-a",
            "files": {
                "transition_render": {"url": "/render.wav"},
                "transition_render_meta": {"url": "/render.json"},
            },
        }],
    }
    items = sync._file_items(manifest)
    assert [(x.get("song_id") or x.get("pair_id"), x["kind"]) for x in items] == [
        ("song-a", "original"), ("song-a", "vocals"), ("song-a", "drums"),
        ("song-a", "bass"), ("song-a", "other"),
        ("pair-a", "transition_render"), ("pair-a", "transition_render_meta"),
    ]


def test_cache_validation_rejects_truncated_sidecar(tmp_path):
    sync = _load()
    path = tmp_path / "original.mp3"
    path.write_bytes(b"abc")
    sync._sidecar(path).write_text(json.dumps({"sha256": "expected", "size": 10, "mtime_ns": path.stat().st_mtime_ns}), encoding="utf-8")
    assert not sync._already_valid(path, "expected", 10)


def test_pair_cache_requires_both_final_files_and_valid_meta(tmp_path):
    sync = _load()
    sync.CACHE_DIR = tmp_path
    pair = tmp_path / "default-mix" / "pairs" / "pair-ready"
    pair.mkdir(parents=True)
    (pair / "transition_render.wav").write_bytes(b"RIFF" + b"0" * 128)
    (pair / "transition_render_meta.json").write_text(json.dumps({"pair_id": "pair-ready"}), encoding="utf-8")
    assert sync._pair_cache_ready("pair-ready") == (True, None)
    (pair / "transition_render_meta.json").write_text("{}", encoding="utf-8")
    assert sync._pair_cache_ready("pair-ready") == (False, "meta_empty")
    (pair / "transition_render.wav").unlink()
    assert sync._pair_cache_ready("pair-ready")[0] is False


def test_stale_pair_cache_is_removed_when_renderer_changes(tmp_path):
    sync = _load()
    sync.CACHE_DIR = tmp_path
    pair = tmp_path / "default-mix" / "pairs" / "pair-stale"
    pair.mkdir(parents=True)
    (pair / "transition_render.wav").write_bytes(b"old")
    (pair / "transition_render_meta.json").write_text(json.dumps({"renderer_version": "old"}), encoding="utf-8")
    item = sync._file_items({"default_mix_pairs": [{"pair_id": "pair-stale", "renderer_version": "new", "files": {"transition_render": {"url": "/r"}}}]})
    sync._invalidate_stale_pair_caches(item)
    assert not (pair / "transition_render.wav").exists()
    assert not (pair / "transition_render_meta.json").exists()


def test_priority_sync_replaces_active_task_and_waits():
    sync = _load()

    async def run():
        async def old():
            await asyncio.Event().wait()

        sync._sync_task = asyncio.create_task(old())
        await sync.state.reset(1, "rolling")

        async def no_network(manifest, *, items=None, state_initialized=False):
            for _ in items or []:
                await sync.state.mark_done()
            await sync.state.finish()

        sync._run_sync = no_network
        result = await sync.sync({"plan_id": "priority", "priority": True, "wait": True, "tracks": [], "default_mix_pairs": []})
        assert result["sync_completed"] is True
        assert result["status"]["plan_id"] == "priority"
        assert result["status"]["running"] is False

    asyncio.run(run())


def test_concurrent_same_asset_download_publishes_once(tmp_path):
    sync = _load()
    sync.CACHE_DIR = tmp_path
    sync._download_locks.clear()

    async def run():
        calls = 0

        async def fake_download(_client, _url, path, _headers):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            path.write_bytes(b"RIFF" + b"0" * 128)

        sync._download_with_httpx = fake_download
        item = {"pair_id": "pair-concurrent", "kind": "transition_render", "info": {"url": "http://test/render.wav"}}
        await sync.state.reset(2, "pair-plan")
        await asyncio.gather(
            sync._download_one(object(), dict(item), asyncio.Semaphore(2)),
            sync._download_one(object(), dict(item), asyncio.Semaphore(2)),
        )
        assert calls == 1
        assert (tmp_path / "default-mix" / "pairs" / "pair-concurrent" / "transition_render.wav").is_file()

    asyncio.run(run())
