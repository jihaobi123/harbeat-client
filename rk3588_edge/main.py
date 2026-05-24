"""RK3588 Edge Agent — FastAPI server for App ↔ RK Audio Engine.

Endpoints:
  GET  /health               — Liveness check
  GET  /state                — Current playback state (JSON)
  WS   /ws                   — Real-time playback state stream
  POST /load_plan            — Load mix plan + trigger sync-worker
  POST /play                 — Start deck playback
  POST /pause                — Pause deck
  POST /stop                 — Stop deck
  POST /xfade                — Trigger crossfade transition
  POST /trigger              — Trigger hardware key / FX
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

# Add project root for stem_automix imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from .config import DeckSide, PlaybackTier, get_config
from .state_manager import StateManager, get_state_manager
from .sync_worker import SyncWorker
from .strategy_selector import StrategySelector
from .session_manager import SessionManager
from .audio_engine import AudioEngine, get_audio_engine

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Singletons
# ═══════════════════════════════════════════════════════════════════════════════

_state: StateManager = get_state_manager()
_sync: SyncWorker = SyncWorker()
_selector: StrategySelector = StrategySelector()
_session: SessionManager = SessionManager()
_engine: AudioEngine = get_audio_engine()


# ═══════════════════════════════════════════════════════════════════════════════
# Lifespan
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RK3588 edge agent starting")
    await _session.start()
    connected = await _engine.connect()
    if connected:
        await _state.set_tier(PlaybackTier.basic)
    else:
        logger.warning("audio engine unavailable — running in API-only mode")
    yield
    logger.info("RK3588 edge agent shutting down")
    await _session.stop()
    await _engine.disconnect()


app = FastAPI(title="HarBeat RK3588 Edge", version="1.0.0", lifespan=lifespan)

# ═══════════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════════

class LoadPlanRequest(BaseModel):
    plan_id: str = Field(..., description="Mix plan identifier")
    mix_plan: dict[str, Any] | None = Field(None, description="Optional inline mix plan")
    manifest: dict[str, Any] | None = Field(None, description="Optional inline manifest")

class PlayRequest(BaseModel):
    deck: str = Field("A", pattern="^(A|B)$")
    start_sec: float = Field(0.0, ge=0.0)

class DeckAction(BaseModel):
    deck: str = Field(..., pattern="^(A|B)$")

class XFadeRequest(BaseModel):
    style: str = Field(..., description="Transition style preset name")
    duration_sec: float = Field(8.0, ge=0.5, le=64.0)
    from_deck: str = Field("A", pattern="^(A|B)$")
    to_deck: str = Field("B", pattern="^(A|B)$")

class TriggerRequest(BaseModel):
    fx_id: int = Field(..., ge=0, le=15)
    deck: str = Field("A", pattern="^(A|B)$")


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    engine_ok = await _engine.health()
    return {
        "ok": True,
        "service": "harbeat-rk3588-edge",
        "audio_engine": engine_ok.get("ok", False),
        "playback_tier": (await _state.get_tier()).value,
    }


@app.get("/state")
async def get_state():
    return {"ok": True, "state": await _state.get_state()}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    await _state.register_ws(ws)
    try:
        # Send current state immediately
        state = await _state.get_state()
        import json
        await ws.send_text(json.dumps({"type": "playback_state", "data": state}))
        # Keep connection alive, handle incoming pings
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                if msg == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await _state.unregister_ws(ws)


@app.post("/load_plan")
async def load_plan(req: LoadPlanRequest):
    """Load a mix plan: trigger sync-worker, then set state."""
    await _session.record("load", plan_id=req.plan_id)

    # If inline manifest provided, skip Jetson fetch
    if req.manifest:
        await _state.set_plan(req.plan_id)
        await _state.set_sync_complete(True)
        return {"ok": True, "plan_id": req.plan_id, "source": "inline"}

    # Trigger sync-worker (runs in background)
    asyncio.create_task(_sync.sync_plan(req.plan_id))
    return {"ok": True, "plan_id": req.plan_id, "source": "jetson",
            "message": "sync started"}


@app.post("/play")
async def play(req: PlayRequest):
    deck = DeckSide(req.deck)
    try:
        result = await _engine.play(deck, req.start_sec)
        return {"ok": True, "result": result}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/pause")
async def pause(req: DeckAction):
    deck = DeckSide(req.deck)
    try:
        result = await _engine.pause(deck)
        return {"ok": True, "result": result}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/stop")
async def stop(req: DeckAction):
    deck = DeckSide(req.deck)
    try:
        result = await _engine.stop(deck)
        return {"ok": True, "result": result}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/xfade")
async def xfade(req: XFadeRequest):
    """Trigger crossfade transition."""
    try:
        result = await _engine.crossfade(
            style=req.style,
            duration_sec=req.duration_sec,
            from_deck=DeckSide(req.from_deck),
            to_deck=DeckSide(req.to_deck),
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/trigger")
async def trigger(req: TriggerRequest):
    """Trigger hardware key FX."""
    try:
        result = await _engine.trigger(req.fx_id, DeckSide(req.deck))
        return {"ok": True, "result": result}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/strategy/select")
async def strategy_select(payload: dict[str, Any]):
    """Select the best transition strategy for a track pair.

    Body: {"from_track": {...}, "to_track": {...}, "duration_bars": 8, "force_preset": null}
    """
    from_track = payload.get("from_track", {})
    to_track = payload.get("to_track", {})
    duration_bars = int(payload.get("duration_bars", 8))
    force_preset = payload.get("force_preset")

    result = _selector.select(from_track, to_track, duration_bars, force_preset)
    return {
        "ok": True,
        "preset": result.preset,
        "mode": result.mode,
        "confidence": result.confidence,
        "tier": result.tier,
        "scores": result.scores,
        "plan": result.plan,
        "warnings": result.warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    config = get_config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
