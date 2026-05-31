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
