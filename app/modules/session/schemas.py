"""C6 Session data schemas — the standardized interfaces between modules.

All inter-module communication uses these schemas.
No module imports another module's internal implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# Session state
# ═══════════════════════════════════════════════════════════════════════════════

class SessionState(str, Enum):
    setup = "setup"           # 活动前配置
    warmup = "warmup"         # 暖场
    build = "build"           # 升温
    peak = "peak"             # 高潮
    recover = "recover"       # 回落/恢复
    hold = "hold"             # 保持/延长
    emergency = "emergency"   # 紧急救场
    close = "close"           # 结束


class SceneType(str, Enum):
    cypher = "cypher"
    practice = "practice"
    party = "party"
    battle_warmup = "battle_warmup"
    showcase = "showcase"


class EnergyLevel(str, Enum):
    low = "low"        # 1-2
    medium = "medium"  # 3
    high = "high"      # 4
    peak = "peak"      # 5


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SceneConfig:
    scene: SceneType = SceneType.cypher
    dance_styles: list[str] = field(default_factory=list)  # ["hiphop", "house"]
    energy_start: EnergyLevel = EnergyLevel.medium
    target_duration_min: int = 30
    avoid_tags: list[str] = field(default_factory=list)  # ["too_commercial"]
    prefer_tags: list[str] = field(default_factory=list)  # ["underground"]


@dataclass
class SafetyPoolConfig:
    min_tracks: int = 10
    max_tracks: int = 30
    require_local_cache: bool = True
    allowed_bpm_range: tuple[float, float] = (75, 145)


@dataclass
class SessionConfig:
    scene: SceneConfig = field(default_factory=SceneConfig)
    safety_pool: SafetyPoolConfig = field(default_factory=SafetyPoolConfig)
    undo_depth: int = 10
    queue_buffer_size: int = 3
    offline_mode: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Inter-module communication
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ButtonIntent:
    """C5 → C6: user pressed a button."""
    action: str  # "next", "energy_up", "energy_down", "loop", "style_change",
                 # "undo", "talkover", "emergency_next", "hold", "pause"
    source: str = "app"  # "app" | "hardware"
    timestamp: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate:
    """C3 → C6: a candidate track for the next transition."""
    track_id: str
    score: float = 0.0
    reason: str = ""
    template: str = "safe_blend"  # recommended transition template
    energy_fit: float = 0.0
    bpm_ratio: float = 1.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class CandidateList:
    """C3 → C6: ordered candidate tracks."""
    candidates: list[Candidate] = field(default_factory=list)
    best: Candidate | None = None
    safe: Candidate | None = None
    diverse: Candidate | None = None
    fallback_track_id: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ControlCommand:
    """C6 → C4: playback engine command."""
    action: str  # "play", "xfade", "loop", "duck", "pause", "resume",
                 # "emergency_cut", "stop"
    params: dict[str, Any] = field(default_factory=dict)
    execute_at: str = "next_phrase"  # "now" | "next_beat" | "next_bar" | "next_phrase"
    quantize: bool = True


@dataclass
class UndoableAction:
    """A reversible action stored in the undo stack."""
    action: str
    prev_track_id: str = ""
    prev_position_sec: float = 0.0
    prev_state: SessionState | None = None
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# Session snapshot (for persistence / state restoration)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SessionSnapshot:
    session_id: str = ""
    state: SessionState = SessionState.setup
    scene: SceneConfig = field(default_factory=SceneConfig)
    current_track_id: str = ""
    current_position_sec: float = 0.0
    current_energy: float = 0.5
    queue: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    safety_pool_ids: list[str] = field(default_factory=list)
    undo_depth: int = 0
    energy_history: list[float] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
