from pydantic import BaseModel
from typing import List, Optional, Any

class StandardResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Optional[Any] = None

# --- 添加歌曲到歌单的请求 ---
class AddTrackRequest(BaseModel):
    track_id: int
    sort_order: int
    sync_bpm: bool = False
    transition_type: str = "none" # "none", "fade", "cut_drop"
    transition_duration: int = 0

# --- 获取歌单详情的响应 (聚合数据) ---
class PlaylistItemData(BaseModel):
    playlist_track_id: int
    track_id: int
    sort_order: int
    # DJ 配置
    sync_bpm: bool
    transition_type: str
    transition_duration: int
    # 冗余部分 3.3 模块的歌曲特征，供前端音频引擎使用
    bpm: Optional[float]
    original_url: str

class PlaylistDetailData(BaseModel):
    playlist_id: int
    name: str
    tracks: List[PlaylistItemData]
