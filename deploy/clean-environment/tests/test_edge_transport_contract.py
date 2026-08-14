from __future__ import annotations

import asyncio
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(Path(__file__).parents[1]))
for module_src in (REPO_ROOT / "modules").glob("*/src"):
    sys.path.insert(0, str(module_src))

from adapters.config import AdapterConfig
from adapters.edge_transport import install_edge_routes
from harbeat_transition_orchestrator import accept_task


def edge_config(root: Path) -> AdapterConfig:
    return AdapterConfig.from_mapping({
        "schema_version": 1,
        "service": "edge-agent",
        "profile": "rk3588",
        "mode": "shadow",
        "state_root": str(root / "edge"),
        "asset_root": str(root / "assets"),
        "settings": {
            "sync_worker_url": "http://127.0.0.1:19100",
            "audio_socket": str(root / "audio.sock"),
        },
    })


def transition_request(transition_id: str = "transition-1234") -> dict:
    renderer = "three_band_default_v7_standalone_curve_no_energy_floor"
    source = "dj_structure_precomputed_window_v2"
    plan = {
        "transition_id": transition_id,
        "pair_id": "pair-a-b",
        "from_song_id": "a",
        "to_song_id": "b",
        "from_at_sec": 14.5,
        "audio_feature_source": source,
        "renderer_version": renderer,
        "default_mix": {
            "pair_id": "pair-a-b",
            "from_song_id": "a",
            "to_song_id": "b",
            "from_at_sec": 14.5,
            "audio_feature_source": source,
            "renderer_version": renderer,
        },
    }
    manifest = {
        "pair_id": "pair-a-b",
        "audio_feature_source": source,
        "renderer_version": renderer,
        "files": {
            "transition_render": {"url": "https://jetson/render.wav"},
            "transition_render_meta": {"url": "https://jetson/render.json"},
        },
    }
    return {
        "transition_id": transition_id,
        "trigger": "fast_cut",
        "from_song_id": "a",
        "to_song_id": "b",
        "transition_plan": plan,
        "default_mix_pair_manifest": manifest,
        "min_lead_sec": 1.5,
    }


class FakeAudio:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.state = {
            "ok": True,
            "playing": True,
            "paused": False,
            "current_song_id": "a",
            "position_sec": 2.0,
            "duration_sec": 180.0,
            "last_transition": {},
        }

    def __call__(self, _socket_path: str, payload: dict) -> dict:
        self.calls.append(dict(payload))
        cmd = payload["cmd"]
        if cmd in {"state", "ping"}:
            return dict(self.state)
        if cmd == "play":
            self.state.update(current_song_id=payload["song_id"], position_sec=payload["start_at_sec"], playing=True)
            return {"ok": True, "song_id": payload["song_id"], "position_sec": payload["start_at_sec"]}
        if cmd == "prepare_default_render":
            return {"ok": True, "action": "default_render_prepared", "pair_id": "pair-a-b", "degraded": False}
        if cmd == "schedule_default_render":
            return {
                "ok": True,
                "action": "default_render_scheduled",
                "transition_id": payload["transition_plan"]["transition_id"],
                "pair_id": "pair-a-b",
                "from_song_id": "a",
                "to_song_id": "b",
                "remaining_lead_sec": 12.5,
                "playback_tier": "default_render_playback",
                "degraded": False,
            }
        return {"ok": True, "action": cmd}


class EdgeTransportContractTests(unittest.TestCase):
    def make_client(self, root: Path) -> tuple[TestClient, FakeAudio, FastAPI]:
        fake = FakeAudio()
        app = FastAPI()
        install_edge_routes(app, edge_config(root), fake)
        return TestClient(app), fake, app

    def test_mobile_required_routes_are_present(self):
        with tempfile.TemporaryDirectory() as directory:
            client, _fake, app = self.make_client(Path(directory))
            del client
            paths = set(app.openapi()["paths"])
            required = {
                "/state", "/play", "/pause", "/resume", "/seek", "/stem_solo",
                "/trigger", "/xfade", "/prefetch", "/cache/validate",
                "/autoplay/default/start", "/autoplay/default/prefetch",
                "/autoplay/default/render", "/autoplay/default/render/prepare",
                "/autoplay/default/render/schedule", "/autoplay/default/render/prepare-schedule",
                "/autoplay/default/render/orchestrate",
                "/autoplay/default/render/orchestrate/{transition_id}",
            }
            self.assertEqual(required - paths, set())

    def test_transport_routes_forward_to_audio_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            client, fake, _app = self.make_client(Path(directory))
            self.assertEqual(client.get("/state").json()["current_song_id"], "a")
            response = client.post("/play", json={"song_id": "b", "start_at_sec": 3.25, "load_stems": False})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(fake.calls[-1]["cmd"], "play")
            self.assertEqual(fake.calls[-1]["start_at_sec"], 3.25)
            self.assertFalse(fake.calls[-1]["load_stems"])

    def test_orchestration_prepares_schedules_and_reuses_once(self):
        with tempfile.TemporaryDirectory() as directory:
            client, fake, app = self.make_client(Path(directory))
            runtime = app.state.edge_runtime
            runtime.http_json = AsyncMock(return_value={"ok": True, "exists": True})
            request = transition_request()
            with client:
                first = client.post("/autoplay/default/render/orchestrate", json=request)
                self.assertEqual(first.status_code, 202, first.text)
                deadline = time.monotonic() + 2.0
                task = first.json()
                while task["state"] != "scheduled" and time.monotonic() < deadline:
                    time.sleep(0.02)
                    task = client.get("/autoplay/default/render/orchestrate/transition-1234").json()
                self.assertEqual(task["state"], "scheduled", task)
                self.assertEqual([call["cmd"] for call in fake.calls].count("prepare_default_render"), 1)
                self.assertEqual([call["cmd"] for call in fake.calls].count("schedule_default_render"), 1)
                second = client.post("/autoplay/default/render/orchestrate", json=request)
                self.assertEqual(second.status_code, 202, second.text)
                self.assertEqual(second.json()["state"], "scheduled")
                self.assertEqual([call["cmd"] for call in fake.calls].count("schedule_default_render"), 1)

    def test_reconcile_does_not_guess_execution_from_target_song(self):
        with tempfile.TemporaryDirectory() as directory:
            _client, fake, app = self.make_client(Path(directory))
            runtime = app.state.edge_runtime
            request = runtime.normalize(transition_request())
            task = accept_task(request, now="test", deadline_epoch_sec=time.time() + 10)
            task["state"] = "scheduled"
            runtime.tasks[task["transition_id"]] = task
            fake.state.update(
                current_song_id="b",
                last_transition={
                    "transition_id": "a-different-transition",
                    "action": "default_render_playback",
                },
            )
            reconciled = asyncio.run(runtime.reconcile_task(task["transition_id"]))
            self.assertEqual(reconciled["state"], "scheduled")


if __name__ == "__main__":
    unittest.main()
