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


class XfadeRequest(BaseModel):
    to_song_id: int | str
    fade_sec: float = Field(default=8.0, ge=0.05, le=30.0)
    to_at_sec: float = 0.0
    style: str = "blend"
    # Phase 2: tempo_A / tempo_B. RK uses pre-rendered .rb.{ratio}.wav
    # if available; ignored when None or outside ±6%.
    tempo_ratio: float | None = None
    # Phase 3.2: per-stem envelope curves; engine consults these only when
    # both decks have all 4 stems loaded. None = legacy single-buffer fade.
    stem_curves: dict[str, Any] | None = None


class PrewarmBeatmatchRequest(BaseModel):
    song_id: int | str
    tempo_ratio: float = Field(ge=0.5, le=2.0)


class PrefetchRequest(BaseModel):
    """Decode wav + 4 stems for the given songs into audio-engine's in-memory
    prefetch cache so the next /xfade lands instantly (no 300ms-2s file IO
    inside deck.load). Mobile calls this when remaining ≤30s in current track.
    """
    song_ids: list[int | str] = Field(min_length=1, max_length=8)


class BeatReinforceRequest(BaseModel):
    """Phase 2.5 — overlay rhythm samples on weak-beat tracks during transitions."""
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(ge=0.0)
    beats: list[float] = Field(default_factory=list)
    sample_key: int = Field(default=4, ge=1, le=5)
    gain: float = Field(default=1.0, ge=0.0, le=3.0)
    pattern: Literal["all", "half", "backbeat"] = "all"


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
    device_id: str | None = None
    name: str | None = None
    tailscale_url: str | None = None
    gateway_url: str | None = None


class RKPlaybackState(BaseModel):
    type: Literal["playback_state"] = "playback_state"
    ts: int
    playing: bool = False
    paused: bool = False
    current_song_id: int | str | None = None
    position_sec: float = 0.0
    duration_sec: float = 0.0
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
