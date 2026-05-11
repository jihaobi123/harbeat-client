"""Voice command API endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from app.shared.responses import APIResponse
from app.modules.voice.keyword_matcher import build_mix_command, match_intent
from app.modules.voice.schemas import VoiceCommandRequest, VoiceCommandResponse

router = APIRouter()

_INTENT_ACTIONS = {
    "play": "Start playback",
    "pause": "Pause playback",
    "hold": "Hold current position",
    "release": "Release hold, resume playback",
    "next": "Skip to next track",
    "lift_energy": "Energy lift requested",
    "drop_energy": "Energy drop requested",
    "switch_style": "Switch dance style",
    "emergency_stop": "Emergency stop — kill all audio",
    "noop": "Command not recognized",
}


@router.post("/command", response_model=APIResponse[VoiceCommandResponse])
def voice_command_endpoint(payload: VoiceCommandRequest):
    """Receive transcribed voice text, resolve intent, return command.

    Flow:
    1. Keyword matching with priority disambiguation
    2. Build MixCommand payload for the resolved intent
    3. Return intent + command payload for the caller to enqueue
    """
    intent, confidence, matched_kw, cmd_payload = match_intent(
        text=payload.text,
        language_hint=payload.language_hint,
    )

    mix_cmd = build_mix_command(intent, cmd_payload)

    return APIResponse(
        data=VoiceCommandResponse(
            intent=intent,
            confidence=round(confidence, 4),
            matched_keywords=matched_kw,
            command_payload=mix_cmd,
            action_taken=_INTENT_ACTIONS.get(intent, "Unknown action"),
            error=None if intent != "noop" else "No matching voice command",
        )
    )
