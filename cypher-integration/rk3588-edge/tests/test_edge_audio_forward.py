import asyncio
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "edge-agent"))


def _load_main():
    spec = importlib.util.spec_from_file_location("edge_agent_main_for_forward_test", ROOT / "edge-agent" / "main.py")
    main = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(main)
    return main


def test_forward_uses_long_timeout_for_decode_heavy_audio_commands(monkeypatch):
    main = _load_main()
    calls = []

    class FakeAudioClient:
        def send_command(self, body, timeout=None):
            calls.append((body, timeout))
            return {"ok": True}

    async def run():
        monkeypatch.setattr(main, "audio_client", FakeAudioClient())
        await main._forward("xfade", to_song_id="b", fade_sec=4.0, style="blend")

    asyncio.run(run())

    assert calls[0][0]["cmd"] == "xfade"
    assert calls[0][1] >= 30.0


def test_eq_band_mix_is_decode_heavy_command():
    main = _load_main()

    assert "xfade_eq_band_mix" in main.DECODE_HEAVY_AUDIO_COMMANDS
    assert "prewarm_beatmatch" in main.DECODE_HEAVY_AUDIO_COMMANDS


def test_mix_effect_routes_are_registered():
    main = _load_main()

    route_paths = {getattr(route, "path", "") for route in main.app.routes}

    assert "/apply_filter" in route_paths
    assert "/apply_loudness_norm" in route_paths
    assert "/xfade_mix_effects" in route_paths


def test_mix_effect_rest_endpoints_forward_to_audio_engine(monkeypatch):
    main = _load_main()
    calls = []

    async def fake_forward(cmd, **payload):
        calls.append((cmd, payload))
        return {"ok": True, "playback_tier": "non_stem", "style": payload.get("style")}

    async def run():
        monkeypatch.setattr(main, "_forward", fake_forward)
        await main.apply_filter(main.ApplyFilterRequest(
            deck="active",
            filter_type="highpass",
            cutoff_hz=800.0,
            q=0.9,
        ))
        await main.apply_loudness_norm(main.ApplyLoudnessNormRequest(
            deck="active",
            gain_db=-2.5,
            target_lufs=-14.0,
        ))
        await main.xfade_mix_effects(main.XfadeRequest(
            to_song_id="next-song",
            fade_sec=4.0,
            style="rise",
        ))

    asyncio.run(run())

    assert calls[0] == (
        "apply_filter",
        {"deck": "active", "filter_type": "highpass", "cutoff_hz": 800.0, "q": 0.9},
    )
    assert calls[1] == (
        "apply_loudness_norm",
        {"deck": "active", "gain_db": -2.5, "target_lufs": -14.0},
    )
    assert calls[2][0] == "xfade"
    assert calls[2][1]["to_song_id"] == "next-song"
    assert calls[2][1]["style"] == "rise"
