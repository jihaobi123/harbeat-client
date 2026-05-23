"""协议 P4/P5/P8 的 Pydantic 模型（骨架版）。"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlayRequest(BaseModel):
    song_id: int | str
    start_at_sec: float = 0.0


class SeekRequest(BaseModel):
    sec: float


class TriggerRequest(BaseModel):
    key: int = Field(ge=0, le=9)


class StemSoloRequest(BaseModel):
    # 传 None / 传起不有 stem 字段 都表示取消 solo
    stem: Literal["vocals", "drums", "bass", "other"] | None = None


class DeckEqRequest(BaseModel):
    """DJ 风 3-band EQ：80Hz low-shelf / 1kHz peak / 8kHz high-shelf。
    每个 band 限幅 ±12 dB；0.0 = 平直（bypass，零开销）。"""

    deck: Literal["a", "b", "active", "inactive"] = "active"
    low_db: float = Field(default=0.0, ge=-12.0, le=12.0)
    mid_db: float = Field(default=0.0, ge=-12.0, le=12.0)
    hi_db: float = Field(default=0.0, ge=-12.0, le=12.0)


class XfadeRequest(BaseModel):
    to_song_id: int | str
    fade_sec: float = Field(default=4.0, ge=0.05, le=30.0)
    to_at_sec: float = Field(default=0.0, ge=0.0)
    # DJ + Spotify Mix 风格 preset，对应 Jetson transition_type / App 手动切歌。
    style: Literal[
        "smooth", "power", "bass_swap", "echo_out", "filter", "cut", "slam",
        "fade", "rise", "blend", "wave", "melt",
    ] = "smooth"


class PrefetchRequest(BaseModel):
    """提前把候选歌曲的 PCM+stems 解码到 RK 内存，按键切歌即取即用。"""

    song_ids: list[int | str] = Field(default_factory=list, max_length=8)


class LoadPlanRequest(BaseModel):
    mix_plan: dict[str, Any]
    manifest: dict[str, Any]


class HealthResponse(BaseModel):
    ok: bool = True
    audio_ready: bool = False
    audio_socket: str
    current_song_id: int | str | None = None
    plan_id: str | None = None
    session_id: str | None = None
    sync_status: dict[str, Any] | None = None


class RKPlaybackState(BaseModel):
    type: Literal["playback_state"] = "playback_state"
    ts: int
    playing: bool = False
    paused: bool = False
    current_song_id: int | str | None = None
    position_sec: float = 0.0
    next_song_id: int | str | None = None
    next_transition_in_sec: float | None = None
    active_loops: list[int] = Field(default_factory=list)
    active_stem_fx: str | None = None


class DeviceInfo(BaseModel):
    type: Literal["device_info"] = "device_info"
    ts: int
    cpu_percent: float = 0.0
    mem_used_mb: float = 0.0
    temp_c: float | None = None
    disk_free_gb: float = 0.0
    audio_xrun_count: int = 0
    jetson_reachable: bool = False
    wifi_ssid: str | None = None


class KeyEvent(BaseModel):
    type: Literal["key_event"] = "key_event"
    ts: int
    key: int
    source: Literal["hid", "app"] = "app"
