from pydantic import BaseModel
from typing import List, Optional, Any

class StandardResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Optional[Any] = None

class AnalyzeData(BaseModel):
    track_id: int  # 【核心新增】：返回数据库中的 ID
    bpm: float
    key: str
    tags: List[str]

class SplitData(BaseModel):
    vocals_url: str
    drums_url: str
    bass_url: str
    other_url: str

class CueCreateRequest(BaseModel):
    user_id: int
    track_id: int
    cue_type: str
    start_time: float
    end_time: Optional[float] = None
    name: Optional[str] = None

class CueResponseData(BaseModel):
    id: int
    cue_type: str
    start_time: float
    end_time: Optional[float]
    name: Optional[str]