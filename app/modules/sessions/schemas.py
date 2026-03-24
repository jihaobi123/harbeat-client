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
