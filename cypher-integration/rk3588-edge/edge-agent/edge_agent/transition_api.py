
"""
Transition Plan API — 注册到 edge-agent。
在 edge-agent/main.py 中 import 并注册:

    from edge_agent.transition_api import router as transition_router
    app.include_router(transition_router)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import sys, importlib.util
from pathlib import Path

_cypher_root = Path(__file__).resolve().parent.parent.parent
_audio_engine_dir = str(_cypher_root / "audio-engine")

# strategy_selector / transition_planner 都在 audio-engine/ 下，
# 必须先加到 sys.path 再 import。
if _audio_engine_dir not in sys.path:
    sys.path.insert(0, _audio_engine_dir)

_planner_path = _cypher_root / "audio-engine" / "transition_planner.py"
_spec = importlib.util.spec_from_file_location("transition_planner", str(_planner_path))
_tp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tp)
plan_mix = _tp.plan_mix

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transition", tags=["transition"])


class TransitionPlanRequest(BaseModel):
    song_ids: list[str] = Field(default_factory=list, max_length=32)
    songs: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    stems_available: bool = True
    prefer_exits: dict[str, float] | None = None
    prefer_entries: dict[str, float] | None = None
    optimize_order: bool = False


def _parse_camelot(key_str: str | None) -> int:
    import re
    if not key_str:
        return 1
    m = re.match(r"(\d+)", str(key_str))
    return int(m.group(1)) if m else 1


@router.post("/plan")
async def transition_plan(req: TransitionPlanRequest) -> dict[str, Any]:
    """输入一组 song_id，返回最优过渡方案。

    每对相邻歌曲跑 strategy_selector 评分，自动选最佳窗口和 preset。
    结果可直接喂给 /load_plan。
    """
    try:
        # 优先使用直接传入的歌曲数据；否则从 song_ids 查询
        songs = list(req.songs) if req.songs else []
        if req.song_ids and not songs:
            async with httpx.AsyncClient(timeout=10.0) as client:
                songs = []
                for sid in req.song_ids:
                    song = await _fetch_song(client, sid)
                    if song:
                        songs.append(song)

        if len(songs) < 2:
            return {"ok": False, "error": f"need >=2 valid songs, got {len(songs)}", "plan": None}

        plan = plan_mix(
            songs,
            stems_available=req.stems_available,
            prefer_exits=req.prefer_exits,
            prefer_entries=req.prefer_entries,
            optimize_order=req.optimize_order,
        )
        return {"ok": True, "plan": plan}
    except Exception as exc:
        logger.exception("transition/plan failed")
        return {"ok": False, "error": str(exc), "plan": None}


async def _fetch_song(client: httpx.AsyncClient, sid: str) -> dict | None:
    # 1. Local analysis cache (fast, no network)
    try:
        import json
        from pathlib import Path
        cache_file = Path("/home/cat/cypher/cache/song_analysis.json")
        if cache_file.exists():
            cache = json.loads(cache_file.read_text())
            if sid in cache:
                logger.info("song %s loaded from local cache", sid[:8])
                return cache[sid]
    except Exception:
        pass

    # 2. Plan file fallback
    try:
        plan_file = Path("/home/cat/cypher/plans/current.json")
        if plan_file.exists():
            data = json.loads(plan_file.read_text())
            tracks = data.get("mix_plan", {}).get("tracks", [])
            for t in tracks:
                if t.get("song_id") == sid:
                    return {
                        "song_id": sid,
                        "title": t.get("title", ""),
                        "bpm": t.get("bpm", 120),
                        "camelot": 1,
                        "energy": 0.5,
                        "duration": t.get("duration", 240),
                        "cues": [],
                    }
    except Exception:
        pass

    # Fallback: try Jetson manifest
    try:
        resp = await client.get(f"http://192.168.5.100:8000/api/manifest/song/{sid}")
        if resp.status_code == 200:
            mf = resp.json()
            beats = mf.get("analysis", {}).get("beat_points", [])
            return {
                "song_id": sid,
                "title": mf.get("title", ""),
                "artist": mf.get("artist", ""),
                "bpm": mf.get("bpm", 120),
                "camelot": _parse_camelot(mf.get("camelotKey")),
                "energy": mf.get("energy", 0.5),
                "duration": mf.get("duration", 240),
                "cues": mf.get("analysis", {}).get("cue_points", []),
                "sections": mf.get("analysis", {}).get("segments", []),
                "stem_activity_windows": mf.get("analysis", {}).get("stem_activity_windows", []),
                "beats": beats[:50] if beats else [],
            }
    except Exception:
        pass

    # Last resort
    return {
        "song_id": sid,
        "bpm": 120, "camelot": 1, "energy": 0.5, "duration": 240,
        "cues": [],
    }
