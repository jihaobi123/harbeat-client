"""edge-agent REST API — FastAPI :9000（协议 P4）。"""

from __future__ import annotations

import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException

from edge_agent.audio_client import AudioEngineClient, AudioEngineError, audio_client
from edge_agent.config import settings
from edge_agent.models import (
  DeckEqRequest,
  HealthResponse,
  LoadPlanRequest,
  PlayRequest,
  PrefetchRequest,
  RKPlaybackState,
  SeekRequest,
  StemSoloRequest,
  TriggerRequest,
  XfadeRequest,
)
from edge_agent.state import edge_state

logger = logging.getLogger(__name__)


def _jetson_headers() -> dict[str, str]:
  headers: dict[str, str] = {"Content-Type": "application/json"}
  if settings.jwt_token:
    headers["Authorization"] = f"Bearer {settings.jwt_token}"
  if settings.harbeat_rk_token:
    headers["X-RK-Token"] = settings.harbeat_rk_token
  return headers


async def _flush_events_once() -> bool:
  session_id = edge_state.session_id or edge_state.init_runtime()
  batch = await edge_state.pop_event_batch(settings.event_flush_batch_size)
  if not batch:
    return True
  url = f"{settings.jetson_base_url.rstrip('/')}/api/sessions/rk/{session_id}/events"
  try:
    async with httpx.AsyncClient(timeout=5.0) as client:
      resp = await client.post(
        url,
        headers=_jetson_headers(),
        json={"rk_id": settings.rk_id, "events": batch},
      )
      resp.raise_for_status()
    return True
  except Exception as exc:
    logger.warning("SessionEvent flush failed: %s", exc)
    edge_state.persist_events(batch)
    await edge_state.restore_event_batch_front(batch)
    return False


async def _event_flush_loop() -> None:
  while True:
    await asyncio.sleep(settings.event_flush_interval_sec)
    await _flush_events_once()


def _optional_auth(x_edge_token: str | None = Header(default=None)) -> None:
  if settings.edge_token and x_edge_token != settings.edge_token:
    raise HTTPException(status_code=401, detail="invalid edge token")


async def _forward(cmd: str, **payload: Any) -> dict[str, Any]:
  body = {"cmd": cmd, **payload}
  try:
    result = audio_client.send_command(body)
    if result.get("ok") is False:
      code = int(result.get("code", 503))
      raise HTTPException(status_code=code, detail=result.get("error", "audio-engine error"))
    await edge_state.set_audio_ready(True)
    return result
  except AudioEngineError as exc:
    await edge_state.set_audio_ready(False)
    raise HTTPException(status_code=503, detail=str(exc)) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
  session_id = edge_state.init_runtime()
  ready = audio_client.is_reachable()
  await edge_state.set_audio_ready(ready)
  plan = edge_state.load_current_plan()
  if plan and isinstance(plan.get("mix_plan"), dict):
    await edge_state.set_plan_id(plan["mix_plan"].get("plan_id"))
    if ready:
      try:
        audio_client.send_command({"cmd": "load_plan", "mix_plan": plan["mix_plan"]}, timeout=2.0)
      except AudioEngineError:
        pass
  flush_task = asyncio.create_task(_event_flush_loop())
  logger.info("edge-agent started (audio_ready=%s session_id=%s)", ready, session_id)
  try:
    yield
  finally:
    flush_task.cancel()
    try:
      await _flush_events_once()
    except Exception:
      pass


app = FastAPI(title="Cypher Edge Agent", version="0.1.0", lifespan=lifespan)


@app.get("/api/edge/info", response_model=HealthResponse)
async def edge_info() -> HealthResponse:
    """App compatibility: alias for /health."""
    return await health()


@app.post("/api/edge/pair/start")
async def edge_pair_start():
    """Start device pairing — returns a 6-digit code."""
    import random
    code = f"{random.randint(100000, 999999)}"
    return {"code": 0, "data": {
        "device_id": settings.rk_id,
        "name": f"Cypher Edge ({settings.rk_id})",
        "pair_code": code,
        "expires_in_sec": 120,
    }}


@app.post("/api/edge/pair/confirm")
async def edge_pair_confirm(body: dict[str, Any]):
    """Confirm device pairing — returns a device token."""
    return {"code": 0, "data": {
        "device_id": settings.rk_id,
        "device_token": settings.edge_token or "paired-token",
        "confirmed": True,
    }}


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
  sync_status = None
  try:
    async with httpx.AsyncClient(timeout=1.0) as client:
      resp = await client.get(f"{settings.sync_worker_url.rstrip('/')}/status")
      if resp.status_code == 200:
        sync_status = resp.json()
  except Exception:
    sync_status = {"running": False, "available": False}
  return HealthResponse(
    ok=True,
    audio_ready=edge_state.audio_ready,
    audio_socket=settings.audio_socket,
    current_song_id=edge_state.current_song_id,
    plan_id=edge_state.plan_id,
    session_id=edge_state.session_id,
    sync_status=sync_status,
  )


@app.get("/state", response_model=RKPlaybackState)
async def get_state() -> RKPlaybackState:
  try:
    state = audio_client.send_command({"cmd": "state"}, timeout=1.0)
    if state.get("ok") is not False:
      await edge_state.set_audio_ready(True)
      return await edge_state.replace_playback_from_audio(state)
  except AudioEngineError:
    await edge_state.set_audio_ready(False)
  return await edge_state.snapshot_playback()


@app.post("/play", dependencies=[Depends(_optional_auth)])
async def play(req: PlayRequest) -> dict[str, Any]:
  result = await _forward("play", song_id=req.song_id, start_at_sec=req.start_at_sec)
  pos = float(result.get("position_sec", req.start_at_sec))
  await edge_state.update_playback(
    playing=True,
    paused=False,
    current_song_id=req.song_id,
    position_sec=pos,
  )
  await edge_state.append_event(
    {"type": "play_started", "song_id": req.song_id, "position_sec": req.start_at_sec}
  )
  return {"ok": True, "result": result}


@app.post("/pause", dependencies=[Depends(_optional_auth)])
async def pause() -> dict[str, Any]:
  result = await _forward("pause")
  await edge_state.update_playback(playing=False, paused=True)
  await edge_state.append_event({"type": "pause"})
  return {"ok": True, "result": result}


@app.post("/resume", dependencies=[Depends(_optional_auth)])
async def resume() -> dict[str, Any]:
  result = await _forward("resume")
  await edge_state.update_playback(playing=True, paused=False)
  await edge_state.append_event({"type": "resume"})
  return {"ok": True, "result": result}


@app.post("/next", dependencies=[Depends(_optional_auth)])
async def next_track() -> dict[str, Any]:
  result = await _forward("next")
  await edge_state.append_event({"type": "next"})
  return {"ok": True, "result": result}


@app.post("/xfade", dependencies=[Depends(_optional_auth)])
async def xfade(req: XfadeRequest) -> dict[str, Any]:
  """对任意已缓存歌做主动 crossfade（复刻网页能量/风格切歌的无缝衰接）。"""
  result = await _forward(
    "xfade",
    to_song_id=req.to_song_id,
    fade_sec=req.fade_sec,
    to_at_sec=req.to_at_sec,
    style=req.style,
  )
  await edge_state.update_playback(
    playing=True,
    paused=False,
    current_song_id=req.to_song_id,
    position_sec=req.to_at_sec,
  )
  await edge_state.append_event(
    {
      "type": "xfade",
      "to_song_id": req.to_song_id,
      "fade_sec": req.fade_sec,
      "to_at_sec": req.to_at_sec,
      "style": req.style,
    }
  )
  return {"ok": True, "result": result}


@app.post("/prefetch", dependencies=[Depends(_optional_auth)])
async def prefetch(req: PrefetchRequest) -> dict[str, Any]:
  """预解码候选歌曲到 RK 内存，跳过后续 /xfade 的磁盘 IO。未同步到 RK 的 song_id 会静默忽略。"""
  result = await _forward("prefetch", song_ids=req.song_ids)
  return {"ok": True, "result": result}


@app.post("/stem_solo", dependencies=[Depends(_optional_auth)])
async def stem_solo(req: StemSoloRequest) -> dict[str, Any]:
  """持久 stem solo：传 stem=None 取消。RK 仅播出该 stem。"""
  result = await _forward("stem_solo", stem=req.stem)
  await edge_state.append_event({"type": "stem_solo", "stem": req.stem})
  return {"ok": True, "result": result}


@app.post("/eq", dependencies=[Depends(_optional_auth)])
async def deck_eq(req: DeckEqRequest) -> dict[str, Any]:
  """DJ 风 3-band EQ（0 = bypass）。deck 可设 ‘a’/‘b’/‘active’/‘inactive’。"""
  result = await _forward(
    "set_deck_eq",
    deck=req.deck,
    low_db=req.low_db,
    mid_db=req.mid_db,
    hi_db=req.hi_db,
  )
  return {"ok": True, "result": result}


@app.post("/seek", dependencies=[Depends(_optional_auth)])
async def seek(req: SeekRequest) -> dict[str, Any]:
  result = await _forward("seek", sec=req.sec)
  await edge_state.update_playback(position_sec=req.sec)
  return {"ok": True, "result": result}


@app.post("/trigger", dependencies=[Depends(_optional_auth)])
async def trigger(req: TriggerRequest) -> dict[str, Any]:
  result = await _forward("trigger", key=req.key)
  await edge_state.push_key_event(req.key, source="app")
  if req.key == 0 and isinstance(result, dict):
    action = result.get("action")
    if action == "pause":
      await edge_state.update_playback(playing=False, paused=True)
    elif action == "resume":
      await edge_state.update_playback(playing=True, paused=False)
  return {"ok": True, "result": result}


@app.post("/internal/key_event")
async def internal_key_event(body: dict[str, Any]) -> dict[str, Any]:
  """input-daemon 专用，仅本机调用，不走鉴权。"""
  key = int(body["key"])
  source = body.get("source", "hid")
  await edge_state.push_key_event(key, source=source)
  return {"ok": True}


@app.post("/internal/flush_events", dependencies=[Depends(_optional_auth)])
async def flush_events() -> dict[str, Any]:
  ok = await _flush_events_once()
  return {"ok": ok, "session_id": edge_state.session_id}


@app.post("/load_plan", dependencies=[Depends(_optional_auth)])
async def load_plan(req: LoadPlanRequest) -> dict[str, Any]:
  await _flush_events_once()
  path = edge_state.save_current_plan(req.mix_plan, req.manifest)
  plan_id = req.mix_plan.get("plan_id")
  session_id = await edge_state.start_new_session()
  await edge_state.set_plan_id(plan_id)

  sync_started = False
  sync_error: str | None = None
  try:
    async with httpx.AsyncClient(timeout=5.0) as client:
      resp = await client.post(
        f"{settings.sync_worker_url.rstrip('/')}/sync",
        json={"manifest": req.manifest},
      )
      resp.raise_for_status()
      sync_started = True
  except Exception as exc:
    sync_error = str(exc)
    logger.warning("sync-worker 未就绪: %s", exc)

  # 通知 audio-engine 加载 plan（若已运行）
  try:
    audio_client.send_command({"cmd": "load_plan", "mix_plan": req.mix_plan})
  except AudioEngineError:
    pass

  await edge_state.append_event({"type": "load", "plan_id": plan_id, "session_id": session_id})
  return {
    "ok": True,
    "plan_id": plan_id,
    "session_id": session_id,
    "plan_path": str(path),
    "sync_started": sync_started,
    "sync_error": sync_error,
  }
