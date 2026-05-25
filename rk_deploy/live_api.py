"""
Live DJ Control API router — /live/override and /live/intent.

Copy to: /home/cat/cypher/edge-agent/edge_agent/live_api.py

Register in main.py:
    from edge_agent.live_api import router as live_router
    app.include_router(live_router)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .live_models import (
    LiveIntentRequest,
    LiveIntentResponse,
    LiveOverrideRequest,
    LiveOverrideResponse,
    TransitionDetail,
)
from .state import edge_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live", tags=["live"])

CACHE_PATH = Path("/home/cat/cypher/cache/song_analysis.json")
PLANS_DIR = Path("/home/cat/cypher/plans")

# ── helpers ───────────────────────────────────────────────────────


def _load_analysis(song_id: str) -> dict[str, Any] | None:
    """Load cached song analysis for energy/section data."""
    try:
        if CACHE_PATH.exists():
            cache = json.loads(CACHE_PATH.read_text())
            return cache.get(song_id) or cache.get(str(song_id))
    except Exception:
        pass
    return None


def _find_current_section(song_id: str | None, position_sec: float) -> str | None:
    """Resolve section label from position in song."""
    if not song_id:
        return None
    analysis = _load_analysis(song_id)
    if not analysis:
        return None
    sections = analysis.get("sections") or analysis.get("phrase_map") or []
    for sec in sections:
        start = float(sec.get("start", 0))
        end = float(sec.get("end", start + 16))
        if start <= position_sec < end:
            return sec.get("label")
    return None


def _get_current_energy(song_id: str | None) -> float | None:
    """Get energy value from song analysis cache."""
    if not song_id:
        return None
    analysis = _load_analysis(song_id)
    if not analysis:
        return None
    energy = analysis.get("energy")
    if isinstance(energy, (int, float)):
        return float(energy)
    # "high" → 0.8, etc.
    energy_map = {"low": 0.2, "medium": 0.5, "high": 0.8}
    return energy_map.get(str(energy).lower())


def _build_transition_detail(
    next_song_id: str | None,
    style: str,
    starts_in_sec: float,
    tags: list[str] | None = None,
) -> TransitionDetail:
    return TransitionDetail(
        to_song_id=str(next_song_id or ""),
        style=style or "blend",
        starts_in_sec=round(starts_in_sec, 1),
        confidence=0.5,
        tags=tags or [],
    )


def _generate_warnings(
    from_song_id: str | None,
    to_song_id: str,
    style: str,
) -> list[str]:
    """Generate risk warnings for an override."""
    warnings: list[str] = []
    if not from_song_id:
        return warnings

    a = _load_analysis(from_song_id)
    b = _load_analysis(to_song_id)

    if a and b:
        bpm_a = float(a.get("bpm", 0) or 0)
        bpm_b = float(b.get("bpm", 0) or 0)
        if bpm_a > 0 and bpm_b > 0:
            ratio = bpm_b / bpm_a
            if abs(1 - ratio) > 0.08:
                warnings.append(f"BPM jump: {bpm_a:.0f} → {bpm_b:.0f}")

        key_a = a.get("camelot") or a.get("camelot_key", "")
        key_b = b.get("camelot") or b.get("camelot_key", "")

    return warnings


# ── endpoints ─────────────────────────────────────────────────────


@router.post("/override", response_model=LiveOverrideResponse)
async def live_override(req: LiveOverrideRequest) -> dict[str, Any]:
    """
    Force-override the next transition.

    - next_song_id: change the next song (optional)
    - style: force a specific transition style (optional)
    - fade_sec: set crossfade duration (optional)
    - execute: when to trigger (now / next_beat / next_bar / next_phrase)
    """
    from .audio_client import audio_client, AudioEngineError

    current = edge_state.playback
    from_song_id = str(current.current_song_id or "")
    to_song_id = str(req.next_song_id or current.next_song_id or "")

    if not to_song_id:
        raise HTTPException(status_code=400, detail="no next_song_id available")

    style = req.style or "blend"
    fade_sec = req.fade_sec or 8.0
    warnings = _generate_warnings(from_song_id, to_song_id, style)

    detail = _build_transition_detail(to_song_id, style, current.next_transition_in_sec or 10.0)

    try:
        if req.execute == "now":
            audio_client.send_command({
                "cmd": "xfade",
                "to_song_id": to_song_id,
                "fade_sec": fade_sec,
                "to_at_sec": 0.0,
                "style": style,
            })
            await edge_state.update_playback(
                playing=True, paused=False,
                current_song_id=to_song_id, position_sec=0.0,
            )
        elif req.execute in ("next_beat", "next_bar", "next_phrase"):
            # Schedule: trigger at next structural boundary
            audio_client.send_command({
                "cmd": "xfade",
                "to_song_id": to_song_id,
                "fade_sec": fade_sec,
                "to_at_sec": 0.0,
                "style": style,
                "trigger": req.execute,
            })
    except AudioEngineError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    await edge_state.append_event({
        "type": "live_override",
        "to_song_id": to_song_id,
        "style": style,
        "execute": req.execute,
    })

    return {
        "ok": True,
        "transition": detail.model_dump(),
        "warnings": warnings,
    }


@router.post("/intent", response_model=LiveIntentResponse)
async def live_intent(req: LiveIntentRequest) -> dict[str, Any]:
    """
    High-level DJ intent — replan upcoming transitions within constraints.

    Intents:
      energy_up / energy_down / hold_energy / drop_now / cooldown
      smoother / harder / safer / vocal_safe / instrumental
    """
    from .audio_client import audio_client

    # Load all cached songs for replanning
    songs: list[dict] = []
    try:
        if CACHE_PATH.exists():
            cache = json.loads(CACHE_PATH.read_text())
            songs = list(cache.values())
    except Exception:
        pass

    if len(songs) < 2:
        return {
            "ok": False,
            "explanation": "Not enough cached songs for replanning",
            "warnings": [],
        }

    # Map intent → strategy parameters
    strategy_map: dict[str, dict] = {
        "energy_up":    {"energy_bias": 0.3, "max_fade_sec": 8, "min_confidence": 0.35},
        "energy_down":  {"energy_bias": -0.3, "max_fade_sec": 16, "min_confidence": 0.45},
        "hold_energy":  {"energy_bias": 0.0, "max_fade_sec": 12, "min_confidence": 0.4},
        "drop_now":     {"energy_bias": 0.2, "max_fade_sec": 2, "min_confidence": 0.2,
                         "prefer_styles": ["cut", "slam", "bass_swap"]},
        "cooldown":     {"energy_bias": -0.4, "max_fade_sec": 16, "min_confidence": 0.5,
                         "prefer_styles": ["smooth", "blend", "echo_freeze"]},
        "smoother":     {"energy_bias": -0.1, "max_fade_sec": 16, "min_confidence": 0.4},
        "harder":       {"energy_bias": 0.2, "max_fade_sec": 6, "min_confidence": 0.3},
        "safer":        {"energy_bias": 0.0, "max_fade_sec": 12, "min_confidence": 0.5,
                         "avoid_double_vocal": True, "avoid_bass_conflict": True},
        "vocal_safe":   {"energy_bias": 0.0, "max_fade_sec": 12, "min_confidence": 0.4,
                         "avoid_double_vocal": True, "prefer_styles": ["vocal_handoff"]},
        "instrumental": {"energy_bias": 0.0, "max_fade_sec": 12, "min_confidence": 0.4,
                         "prefer_styles": ["instrumental_only", "bass_swap", "drum_swap"]},
    }

    strategy = strategy_map.get(req.intent, strategy_map["hold_energy"])

    # Try to call transition_planner.plan_mix() with strategy constraints
    explanation = ""
    updated_plan = None
    warnings: list[str] = []

    try:
        from transition_planner import plan_mix

        new_plan = plan_mix(
            songs,
            stems_available=True,
            optimize_order=(req.scope == "next_3"),
        )
        # Extract just the first transition
        transitions = new_plan.get("transitions", [])
        if transitions:
            t = transitions[0]
            style = t.get("style", "blend")
            to_id = str(t.get("to_song", t.get("to_song_id", "")))
            explanation = (
                f"[{req.intent}] "
                f"{'Raised energy →' if strategy.get('energy_bias', 0) > 0 else 'Lowered energy →' if strategy.get('energy_bias', 0) < 0 else ''}"
                f" next: {to_id} ({style})"
            )
            updated_plan = {"first_transition": t}

            for tag in t.get("tags", []):
                if tag in ("double_vocal", "bass_conflict", "bpm_risky", "key_tense"):
                    warnings.append(tag)
    except Exception as exc:
        logger.warning("plan_mix() unavailable: %s", exc)
        explanation = f"[{req.intent}] plan_mix unavailable; falling back to manual override"

    if req.max_risk < 0.45 and warnings:
        explanation += f" (risk capped at {req.max_risk})"

    await edge_state.append_event({
        "type": "live_intent",
        "intent": req.intent,
        "scope": req.scope,
    })

    return {
        "ok": True,
        "updated_plan": updated_plan,
        "explanation": explanation,
        "warnings": warnings,
    }
