import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "edge-agent"))

from edge_agent.state import EdgeState  # noqa: E402


def test_playback_tier_from_audio_state_is_preserved_for_rest_and_ws_payloads():
    async def run():
        state = EdgeState()
        playback = await state.replace_playback_from_audio(
            {
                "playing": True,
                "paused": False,
                "current_song_id": "song-a",
                "position_sec": 12.5,
                "playback_tier": "stem_aware",
            }
        )
        return playback.model_dump()

    payload = asyncio.run(run())

    assert payload["playback_tier"] == "stem_aware"
