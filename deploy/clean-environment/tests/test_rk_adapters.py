from __future__ import annotations

import sys
import tempfile
import unittest
import importlib.util
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(Path(__file__).parents[1]))
for module_src in (REPO_ROOT / "modules").glob("*/src"):
    sys.path.insert(0, str(module_src))

from adapters.config import AdapterConfig, RK_SERVICES
from adapters.rk_app import create_rk_app
from adapters.operation_executor import HttpOperationPorts
from adapters.operation_store import JsonOperationStore
from harbeat_transition_orchestrator import TransitionOperationExecutor


def config(service: str, root: Path) -> AdapterConfig:
    settings = {
        "sync-worker": {"jetson_base_url": "http://127.0.0.1:18000", "runtime_home": str(root / "runtime")},
        "edge-agent": {
            "sync_worker_url": "http://127.0.0.1:19100",
            "audio_socket": str(root / "audio.sock"),
            "runtime_home": str(root / "runtime"),
            "planning_api_url": "http://127.0.0.1:19020",
            "render_worker_url": "http://127.0.0.1:19030",
        },
        "audio-engine": {"audio_socket": str(root / "audio.sock"), "runtime_home": str(root / "runtime")},
        "input-daemon": {
            "edge_agent_url": "http://127.0.0.1:19000",
            "audio_socket": str(root / "audio.sock"),
            "input_device": "/dev/input/shadow-not-opened",
        },
    }[service]
    return AdapterConfig.from_mapping({
        "schema_version": 1,
        "service": service,
        "profile": "rk3588",
        "mode": "shadow",
        "state_root": str(root / service),
        "asset_root": str(root / "assets"),
        "settings": settings,
    })


def transition_request() -> dict:
    renderer = "three_band_default_v7_standalone_curve_no_energy_floor"
    source = "dj_structure_precomputed_window_v2"
    plan = {
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
        "transition_id": "transition-1234",
        "trigger": "fast_cut",
        "from_song_id": "a",
        "to_song_id": "b",
        "transition_plan": plan,
        "pair_manifest": manifest,
        "deadline_epoch_sec": 100.0,
    }


class RkAdapterTests(unittest.TestCase):
    def test_sync_edge_and_input_adapters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sync = TestClient(create_rk_app(config("sync-worker", root)))
            self.assertEqual(sync.get("/health").status_code, 200)
            self.assertEqual(sync.get("/status").status_code, 200)

            edge = TestClient(create_rk_app(config("edge-agent", root)))
            response = edge.post("/transition/validate", json=transition_request())
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["sync_request"]["tracks"], [])
            first = edge.post("/transition/tasks/accept", json=transition_request())
            second = edge.post("/transition/tasks/accept", json=transition_request())
            self.assertFalse(first.json()["reused"])
            self.assertTrue(second.json()["reused"])

            input_app = TestClient(create_rk_app(config("input-daemon", root)))
            routed = input_app.post("/input/route", json={"key": 6, "timestamp": 1.25})
            self.assertEqual(routed.status_code, 200)
            self.assertEqual(routed.json()["audio_trigger_key"], 3)
            self.assertGreater(routed.json()["audio_frame_bytes"], 4)

    def test_audio_adapter_uses_only_configured_shadow_socket(self):
        if importlib.util.find_spec("sounddevice") is None:
            self.skipTest("workstation lacks target-only sounddevice dependency")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_socket = root / "audio.sock"
            with TestClient(create_rk_app(config("audio-engine", root))) as client:
                response = client.get("/health")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["audio_ready"])
                self.assertEqual(response.json()["audio_socket"], str(audio_socket))
                self.assertTrue(audio_socket.exists())
            self.assertFalse(audio_socket.exists())

    def test_edge_runtime_routes_use_audio_socket_only(self):
        if importlib.util.find_spec("sounddevice") is None:
            self.skipTest("workstation lacks target-only sounddevice dependency")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_client = TestClient(create_rk_app(config("audio-engine", root)))
            edge_client = TestClient(create_rk_app(config("edge-agent", root)))
            with audio_client:
                self.assertEqual(audio_client.get("/health").status_code, 200)
                state = edge_client.get("/runtime/state")
                self.assertEqual(state.status_code, 200, state.text)
                self.assertIn("playing", state.json())
                self.assertEqual(edge_client.post("/runtime/pause").status_code, 200)
                self.assertEqual(edge_client.post("/runtime/resume").status_code, 200)
                self.assertEqual(edge_client.post("/runtime/seek", json={"sec": 1.0}).status_code, 200)

    def test_edge_runtime_routes_keep_transport_errors_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            edge_client = TestClient(create_rk_app(config("edge-agent", root)))

            def fake_audio(_socket_path, payload):
                if payload["cmd"] == "state":
                    return {"ok": True, "playing": True, "position_sec": 2.0}
                return {"ok": True, "cmd": payload["cmd"]}

            with patch("adapters.rk_app._audio_command", side_effect=fake_audio):
                self.assertEqual(edge_client.get("/runtime/state").json()["position_sec"], 2.0)
                self.assertEqual(edge_client.post("/runtime/play", json={"song_id": "song-a"}).status_code, 200)
                self.assertEqual(edge_client.post("/runtime/pause").status_code, 200)
                self.assertEqual(edge_client.post("/runtime/resume").status_code, 200)
                self.assertEqual(edge_client.post("/runtime/seek", json={"sec": 2.0}).status_code, 200)
                self.assertEqual(edge_client.post("/runtime/default-render", json={"command": "bad"}).status_code, 422)

    def test_edge_operation_api_is_persistent_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = {
                "device_id": "rk3588-01",
                "session_id": "set-12345678",
                "intent": "style",
                "target_song_id": "song-b",
                "request_id": "request-12345678",
            }
            first_client = TestClient(create_rk_app(config("edge-agent", root)))
            first = first_client.post("/v1/transition-operations", json=body)
            self.assertEqual(first.status_code, 200, first.text)
            operation_id = first.json()["operation"]["operation_id"]
            self.assertFalse(first.json()["reused"])

            second_client = TestClient(create_rk_app(config("edge-agent", root)))
            second = second_client.post("/v1/transition-operations", json=body)
            self.assertTrue(second.json()["reused"])
            self.assertEqual(second.json()["operation"]["operation_id"], operation_id)
            self.assertEqual(second_client.get(f"/v1/transition-operations/{operation_id}").status_code, 200)
            cancelled = second_client.delete(f"/v1/transition-operations/{operation_id}")
            self.assertEqual(cancelled.json()["status"], "cancelled")

    def test_operation_executor_uses_one_plan_render_sync_and_schedule_chain(self):
        class Response:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config("edge-agent", root)
            payloads = []
            plan = {
                "pair_id": "pair-a-b",
                "from_song_id": "song-a",
                "to_song_id": "song-b",
                "from_at_sec": 15.0,
                "to_at_sec": 12.0,
                "duration_sec": 4.0,
                "renderer_version": "three_band_default_v7_standalone_curve_no_energy_floor",
                "default_mix": {
                    "pair_id": "pair-a-b",
                    "from_song_id": "song-a",
                    "to_song_id": "song-b",
                    "from_at_sec": 15.0,
                    "to_at_sec": 12.0,
                    "duration_sec": 4.0,
                    "audio_feature_source": "dj_structure_precomputed_window_v2",
                    "renderer_version": "three_band_default_v7_standalone_curve_no_energy_floor",
                },
            }
            pair_manifest = {
                "pair_id": "pair-a-b",
                "audio_feature_source": "dj_structure_precomputed_window_v2",
                "renderer_version": "three_band_default_v7_standalone_curve_no_energy_floor",
                "files": {
                    "transition_render": {"url": "/render/artifacts/pair-a-b/transition_render.wav"},
                    "transition_render_meta": {"url": "/render/artifacts/pair-a-b/transition_render.json"},
                },
            }

            def fake_request(method, url, json=None, timeout=None):
                payloads.append((method, url, json))
                if url.endswith("/planning/database/transition"):
                    return Response(plan)
                if url.endswith("/render/database/transition"):
                    return Response({"pair_manifest": pair_manifest, "pair_id": "pair-a-b"})
                if url.endswith("/render/database/song/song-b/manifest"):
                    return Response({"song_id": "song-b", "files": {"original": {"url": "/render/database/song/song-b/original"}}})
                if url.endswith("/sync"):
                    return Response({"ok": True, "sync_completed": True, "status": {"completed": 2, "total": 2, "errors": []}})
                raise AssertionError(url)

            store = JsonOperationStore(root / "operations.json")
            operation, _ = store.create_or_reuse({
                "device_id": "rk3588-01",
                "session_id": "set-12345678",
                "intent": "style",
                "target_song_id": "song-b",
                "request_id": "request-12345678",
            })
            operation_id = operation["operation_id"]
            states = iter([
                {"ok": True, "playing": True, "paused": False, "current_song_id": "song-a", "next_song_id": "song-b", "position_sec": 3.0},
                {"ok": True, "last_transition": {"transition_id": operation_id, "action": "default_render_playback"}},
                {"ok": True, "current_song_id": "song-b", "position_sec": 16.0, "last_transition": {"transition_id": operation_id, "action": "default_render_playback"}},
            ])

            def fake_audio(_path, command):
                if command["cmd"] == "state":
                    return next(states)
                return {"ok": True, "action": command["cmd"]}

            with patch("adapters.operation_executor.httpx.request", side_effect=fake_request), patch(
                "adapters.operation_executor._audio_command", side_effect=fake_audio
            ):
                result = TransitionOperationExecutor(
                    store, HttpOperationPorts(cfg), poll_interval_sec=0.0
                ).execute(operation_id)

            self.assertEqual(result["status"], "succeeded", result)
            self.assertEqual(result["plan"]["transition_id"], operation_id)
            self.assertEqual(result["sync"]["completed"], 2)
            self.assertEqual(sum(url.endswith("/sync") for _, url, _ in payloads), 2)
            planning = next(body for _, url, body in payloads if url.endswith("/planning/database/transition"))
            self.assertEqual(planning["mode"], "fast")
            self.assertEqual(planning["options"]["min_exit_sec"], 15.0)

    def test_all_rk_services_are_registered_and_shadow_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for service in RK_SERVICES - {"audio-engine"}:
                response = TestClient(create_rk_app(config(service, root))).get("/health")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["service"], service)
                self.assertEqual(response.json()["mode"], "shadow")
                self.assertFalse(response.json()["production_ready"])


if __name__ == "__main__":
    unittest.main()
