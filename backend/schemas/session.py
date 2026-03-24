from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime

# 通用响应结构 (复用思维)
class StandardResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Optional[Any] = None

# --- Start Session ---
class SessionStartRequest(BaseModel):
    user_id: int
    mode: str

class SessionStartData(BaseModel):
    session_id: int

# --- Session Event ---
class SessionEventRequest(BaseModel):
    session_id: int
    event_type: str
    event_value: str
    timestamp: datetime

class SuccessData(BaseModel):
    success: bool = True

# --- End Session ---
class SessionEndRequest(BaseModel):
    session_id: int