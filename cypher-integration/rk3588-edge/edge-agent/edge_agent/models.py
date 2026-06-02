"""协议 P4/P5/P8 的 Pydantic 模型（骨架版）。"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class PlayRequest(BaseModel):
    song_id: Union[int, str]
    start_at_sec: float = 0.0


class SeekRequest(BaseModel):
    sec: float


class TriggerRequest(BaseModel):
    key: int = Field(ge=0, le=9)


class StemSoloRequest(BaseModel):
    # 传 None / 传起不有 stem 字段 都表示取消 solo
    stem: Optional[Literal["vocals", "drums", "bass", "other"]] = None


class DeckEqRequest(BaseModel):
    """DJ 风 3-band EQ：80Hz low-shelf / 1kHz peak / 8kHz high-shelf。
    每个 band 限幅 ±12 dB；0.0 = 平直（bypass，零开销）。"""

    deck: Literal["a", "b", "active", "inactive"] = "active"
    low_db: float = Field(default=0.0, ge=-12.0, le=12.0)
    mid_db: float = Field(default=0.0, ge=-12.0, le=12.0)
    hi_db: float = Field(default=0.0, ge=-12.0, le=12.0)


class XfadeRequest(BaseModel):
    transition_id: Optional[str] = None
    to_song_id: Union[int, str]
    fade_sec: float = Field(default=4.0, ge=0.05, le=30.0)
    to_at_sec: float = Field(default=0.0, ge=0.0)
    # DJ + Spotify Mix 风格 preset，对应 Jetson transition_type / App 手动切歌。
    style: Literal[
        "smooth", "power", "bass_swap", "echo_out", "filter", "cut", "slam",
        "fade", "rise", "blend", "wave", "melt", "vocal_handoff", "vocal_ducking",
        "drum_swap", "instrumental_only", "vocal_solo_intro", "echo_freeze",
    ] = "smooth"
    fallback_style: Optional[str] = None
    tempo_ratio: Optional[float] = None
    stem_curves: Optional[dict[str, Any]] = None
    eq_curves: Optional[dict[str, Any]] = None
    phase_anchor_sec: Optional[float] = None


class PrefetchRequest(BaseModel):
    """提前把候选歌曲的 PCM+stems 解码到 RK 内存，按键切歌即取即用。"""

    song_ids: list[Union[int, str]] = Field(default_factory=list, max_length=8)


class PrewarmBeatmatchRequest(BaseModel):
    song_id: Union[int, str]
    tempo_ratio: Optional[float] = None
    tempo_multiplier: Optional[float] = None


class BeatReinforceRequest(BaseModel):
    start_sec: float = 0.0
    end_sec: float = 0.0
    beats: list[float] = Field(default_factory=list, max_length=256)
    sample_key: int = Field(default=4, ge=1, le=9)
    gain: float = Field(default=1.0, ge=0.0, le=8.0)
    pattern: Literal["all", "half", "backbeat"] = "all"


class LoadPlanRequest(BaseModel):
    mix_plan: dict[str, Any]
    manifest: dict[str, Any]


class HealthResponse(BaseModel):
    ok: bool = True
    audio_ready: bool = False
    audio_socket: str
    current_song_id: Optional[Union[int, str]] = None
    plan_id: Optional[str] = None
    session_id: Optional[str] = None
    sync_status: Optional[dict[str, Any]] = None


class RKPlaybackState(BaseModel):
    type: Literal["playback_state"] = "playback_state"
    ts: int
    playing: bool = False
    paused: bool = False
    current_song_id: Optional[Union[int, str]] = None
    position_sec: float = 0.0
    next_song_id: Optional[Union[int, str]] = None
    next_transition_in_sec: Optional[float] = None
    active_loops: list[int] = Field(default_factory=list)
    active_stem_fx: Optional[str] = None
    playback_tier: Literal["basic", "non_stem", "stem_aware"] = "basic"


class DeviceInfo(BaseModel):
    type: Literal["device_info"] = "device_info"
    ts: int
    cpu_percent: float = 0.0
    mem_used_mb: float = 0.0
    temp_c: Optional[float] = None
    disk_free_gb: float = 0.0
    audio_xrun_count: int = 0
    jetson_reachable: bool = False
    wifi_ssid: Optional[str] = None


class KeyEvent(BaseModel):
    type: Literal["key_event"] = "key_event"
    ts: int
    key: int
    source: Literal["hid", "app"] = "app"
