from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SessionStartRequest(BaseModel):
    user_id: int
    mode: str


class SessionStartData(BaseModel):
    session_id: int


class SessionEventRequest(BaseModel):
    session_id: int
    event_type: str
    event_value: Optional[str] = None
    timestamp: datetime


class SessionEndRequest(BaseModel):
    session_id: int


class SuccessData(BaseModel):
    success: bool = True


class InteractionLogRequest(BaseModel):
    user_id: int
    track_id: str
    action_type: str  # play, skip, complete, pause, seek, cue_add, ab_loop
    listen_mode: str = "normal"  # normal, practice, cypher
    current_dance_style: str = ""
    play_duration_sec: float = 0.0
    completion_rate: float = 0.0
    skip_timestamp: Optional[float] = None
    drum_boost_enabled: bool = False
    bpm_adjusted_to: Optional[float] = None
    ab_loop_used: bool = False
    cue_points_added: int = 0
    rewind_count: int = 0


class PracticeListRequest(BaseModel):
    user_id: int
    target_duration: int = 30  # 目标时长（分钟）
    dance_style: Optional[str] = None


class PracticeTrackItem(BaseModel):
    id: str
    title: str
    artist: str
    bpm: Optional[float] = None
    camelot_key: Optional[str] = None
    energy: Optional[float] = None
    duration: float = 0


class PracticeListData(BaseModel):
    user_id: int
    target_duration: int
    tracks: list[PracticeTrackItem]
