"""RK3588 edge-agent configuration — env vars, paths, and constants."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class PlaybackTier(str, Enum):
    basic = "basic"
    non_stem = "non_stem"
    stem_aware = "stem_aware"


class DeckSide(str, Enum):
    A = "A"
    B = "B"


@dataclass
class EdgeConfig:
    """All config driven by env vars with sensible defaults for RK3588."""

    # Network
    host: str = "0.0.0.0"
    port: int = 9100

    # Jetson backend (session events, manifest source)
    jetson_base_url: str = "http://localhost:8000/api"

    # Local cache
    cache_dir: Path = field(default_factory=lambda: Path("/home/cat/cypher/cache"))

    # Audio engine socket
    audio_engine_socket: str = "/tmp/cypher-audio.sock"

    # Manifest download
    download_timeout_sec: int = 120
    max_file_size_mb: int = 500

    # ffmpeg path
    ffmpeg_bin: str = "ffmpeg"

    # Session event flush
    session_flush_interval_sec: int = 10
    session_flush_batch_size: int = 50

    # Expected stem names
    stem_names: tuple[str, ...] = ("vocals", "drums", "bass", "other")

    # Target audio format
    target_sample_rate: int = 44100
    target_channels: int = 2
    target_format: str = "wav"

    def __post_init__(self):
        self.host = os.getenv("EDGE_HOST", self.host)
        self.port = int(os.getenv("EDGE_PORT", str(self.port)))
        self.jetson_base_url = os.getenv("JETSON_BASE_URL", self.jetson_base_url)
        self.cache_dir = Path(os.getenv("CACHE_DIR", str(self.cache_dir)))
        self.audio_engine_socket = os.getenv("AUDIO_ENGINE_SOCKET", self.audio_engine_socket)
        self.download_timeout_sec = int(os.getenv("DOWNLOAD_TIMEOUT_SEC", str(self.download_timeout_sec)))
        self.max_file_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", str(self.max_file_size_mb)))
        self.ffmpeg_bin = os.getenv("FFMPEG_BIN", self.ffmpeg_bin)
        self.session_flush_interval_sec = int(os.getenv("SESSION_FLUSH_INTERVAL_SEC", str(self.session_flush_interval_sec)))
        self.session_flush_batch_size = int(os.getenv("SESSION_FLUSH_BATCH_SIZE", str(self.session_flush_batch_size)))

    def cache_path(self, *parts: str) -> Path:
        p = self.cache_dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


# Singleton
_config: EdgeConfig | None = None


def get_config() -> EdgeConfig:
    global _config
    if _config is None:
        _config = EdgeConfig()
    return _config
