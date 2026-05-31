import asyncio
import sys
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "edge-agent"))


def test_transition_plan_router_is_registered_on_edge_agent_app():
    spec = importlib.util.spec_from_file_location("edge_agent_main_for_test", ROOT / "edge-agent" / "main.py")
    main = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(main)

    route_paths = {getattr(route, "path", "") for route in main.app.routes}

    assert "/transition/plan" in route_paths
    assert "/api/edge/status" in route_paths


def test_fetch_song_uses_configured_jetson_url_and_auth_headers(monkeypatch):
    from edge_agent import transition_api

    seen = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"title": "Configured Jetson", "analysis": {}}

    class FakeClient:
        async def get(self, url, headers=None):
            seen["url"] = url
            seen["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(transition_api.settings, "jetson_base_url", "http://jetson.example:8123")
    monkeypatch.setattr(transition_api.settings, "jwt_token", "jwt-value")
    monkeypatch.setattr(transition_api.settings, "harbeat_rk_token", "rk-value")

    song = asyncio.run(transition_api._fetch_song(FakeClient(), "song-z"))

    assert song["title"] == "Configured Jetson"
    assert seen["url"] == "http://jetson.example:8123/api/manifest/song/song-z"
    assert seen["headers"] == {
        "Authorization": "Bearer jwt-value",
        "X-RK-Token": "rk-value",
    }
