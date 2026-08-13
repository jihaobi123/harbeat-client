from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(Path(__file__).parents[1]))
for module_src in (REPO_ROOT / "modules").glob("*/src"):
    sys.path.insert(0, str(module_src))

from adapters.config import AdapterConfig, AdapterConfigError, JETSON_SERVICES
from adapters.jetson_app import create_jetson_app


SOURCE = "dj_structure_precomputed_window_v2"


def config(service: str, root: Path) -> AdapterConfig:
    return AdapterConfig.from_mapping({
        "schema_version": 1,
        "service": service,
        "profile": "jetson",
        "mode": "shadow",
        "state_root": str(root / service),
        "asset_root": str(root / "assets"),
    })


def song(song_id: str) -> dict:
    duration = 180.0
    bpm = 100.0
    beats = [round(index * 0.6, 3) for index in range(300)]
    return {
        "id": song_id,
        "title": song_id,
        "artist": "test",
        "bpm": bpm,
        "camelot_key": "9A",
        "key": "9A",
        "energy": 0.6,
        "duration": duration,
        "beat_points": beats,
        "downbeats": beats[::4],
        "phrase_map": [{"start": 0.0, "end": 32.0, "label": "intro"}],
        "transition_windows": [],
        "energy_curve": [{"time": 0.0, "energy": 0.6}],
        "stem_activity_windows": [],
        "vocal_events": [],
        "genre_profile": {"vocal_density": 0.2},
        "loudness_profile": {},
        "source_path": "",
        "music_features": {"dj_structure_v2": {
            "version": "dj_structure_v2",
            "track1_exit_candidates": [{
                "time": 14.0,
                "score": 0.9,
                "tail_rms": 0.7,
                "local_rms": 0.7,
                "vocal_sparsity": 0.9,
                "drum_strength": 0.8,
                "immediate_punch": 0.8,
                "handoff_readiness": 0.9,
                "audio_feature_source": SOURCE,
            }],
            "track2_entry_candidates": [{
                "time": 12.0,
                "score": 0.9,
                "entry_rms": 0.7,
                "local_rms": 0.7,
                "vocal_sparsity": 0.9,
                "vocal_entry_sparsity": 0.9,
                "drum_strength": 0.8,
                "drum_entry_strength": 0.8,
                "immediate_punch": 0.8,
                "immediate_entry_punch": 0.8,
                "handoff_readiness": 0.9,
                "audio_feature_source": SOURCE,
            }],
        }},
    }


def analysis_payload() -> dict:
    base = {"audio_feature_source": SOURCE, "time": 4.0, "score": 0.8}
    return {
        "version": "dj_structure_v2",
        "source": "harbeat_dj_structure_analysis_v2",
        "track1_exit_candidates": [{"type": "track1_exit_candidate", **base}],
        "track2_entry_candidates": [{"type": "track2_entry_candidate", **base}],
    }


class JetsonAdapterTests(unittest.TestCase):
    def test_config_rejects_implicit_mode_and_legacy_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = {
                "schema_version": 1,
                "service": "catalog-api",
                "profile": "jetson",
                "state_root": str(root / "state"),
                "asset_root": str(root / "assets"),
            }
            with self.assertRaisesRegex(AdapterConfigError, "shadow mode"):
                AdapterConfig.from_mapping(value)
            value["mode"] = "shadow"
            value["state_root"] = "/".join(("", "home", "mark", "harbeat", "state"))
            with self.assertRaisesRegex(AdapterConfigError, "legacy path"):
                AdapterConfig.from_mapping(value)

    def test_all_jetson_services_expose_identity_health(self):
        with tempfile.TemporaryDirectory() as directory:
            for service in JETSON_SERVICES:
                response = TestClient(create_jetson_app(config(service, Path(directory)))).get("/health")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["service"], service)
                self.assertFalse(response.json()["production_ready"])

    def test_catalog_and_analysis_routes_use_clean_services(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = TestClient(create_jetson_app(config("catalog-api", root)))
            response = catalog.post("/catalog/resolve-playlist", json={
                "playlist_id": 7,
                "songs": [
                    {"id": "lib-a", "song_id": 11, "title": "A", "artist": "AA"},
                    {"id": "lib-b", "song_id": 12, "title": "B", "artist": "BB"},
                ],
                "playlist": {
                    "id": 7,
                    "playlist_name": "test",
                    "songs": [
                        {"song_id": 11, "order_index": 0},
                        {"song_id": 12, "order_index": 1},
                    ],
                },
            })
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["complete"])
            self.assertEqual(len(response.json()["songs"]), 2)

            analysis = TestClient(create_jetson_app(config("analysis-worker", root)))
            response = analysis.post("/analysis/process", json={
                "song_id": "lib-a",
                "features": {},
                "analysis_payload": analysis_payload(),
            })
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["reused"])
            self.assertIn("dj_structure_v2", response.json()["features"])

    def test_planning_route_runs_real_fast_cut_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            client = TestClient(create_jetson_app(config("planning-api", Path(directory))))
            response = client.post("/planning/transition", json={
                "mode": "fast",
                "previous_song": song("a"),
                "next_song": song("b"),
                "options": {"cursor_sec": 10.0, "min_exit_sec": 13.0, "max_exit_sec": 18.0},
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["default_mix"]["audio_feature_source"], SOURCE)
            self.assertGreaterEqual(response.json()["from_at_sec"], 13.0)
            self.assertLessEqual(response.json()["from_at_sec"], 18.0)

    def test_render_and_stem_routes_enforce_configured_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            audio = assets / "song.wav"
            audio.write_bytes(b"test")

            render = TestClient(create_jetson_app(config("render-worker", root)))
            with patch("harbeat_transition_renderer.ensure_reference_render", return_value={"pair_id": "pair-a-b"}):
                response = render.post("/render/transition", json={
                    "previous_song": {"id": "a", "source_path": str(audio)},
                    "next_song": {"id": "b", "source_path": str(audio)},
                    "plan": {"pair_id": "pair-a-b", "default_mix": {"pair_id": "pair-a-b"}},
                })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["pair_id"], "pair-a-b")

            stems = TestClient(create_jetson_app(config("stem-worker", root)))
            output = root / "stem-worker" / "output"
            fake = {name: str(output / f"{name}.wav") for name in ("vocals", "drums", "bass", "other")}
            with patch("harbeat_stem_separation.StemSeparator.separate", return_value=fake):
                response = stems.post("/stems/separate", json={
                    "audio_path": str(audio),
                    "output_root": str(output),
                })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["complete"])
            outside = stems.post("/stems/separate", json={
                "audio_path": str(root / "outside.wav"),
                "output_root": str(output),
            })
            self.assertEqual(outside.status_code, 422)


if __name__ == "__main__":
    unittest.main()
