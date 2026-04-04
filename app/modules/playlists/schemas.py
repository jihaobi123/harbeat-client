from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SongImportItem(BaseModel):
    title: str
    artist: str
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    bpm: Optional[float] = None
    tags: list[str] = []


class PlaylistImportRequest(BaseModel):
    user_id: int
    playlist_name: str
    songs: list[SongImportItem]
    source_type: str = "manual"


class PlaylistImportData(BaseModel):
    playlist_id: int
    import_count: int
    pending_analysis_count: int


class PlaylistSummaryData(BaseModel):
    id: int
    user_id: int
    playlist_name: str
    source_type: str
    song_count: int


class PlaylistSongData(BaseModel):
    song_id: int
    title: str
    artist: str
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    bpm: Optional[int] = None
    tags: list[str] = []
    order_index: int


class PlaylistDetailData(BaseModel):
    id: int
    user_id: int
    playlist_name: str
    source_type: str
    songs: list[PlaylistSongData]


class PlaylistListData(BaseModel):
    playlists: list[PlaylistSummaryData]


class PlaylistSongTagUpdateRequest(BaseModel):
    tags: list[str]


class PlaylistSongOrderItem(BaseModel):
    song_id: int
    order_index: int


class PlaylistReorderRequest(BaseModel):
    songs: list[PlaylistSongOrderItem]


class StyleMixRequest(BaseModel):
    style: str
    duration_minutes: int = 30
    bpm: Optional[int] = None
    energy: Optional[str] = None
    quality_mode: Literal["balanced", "hq", "fast"] = "balanced"


class StyleMixResult(BaseModel):
    playlist: list[PlaylistSongData] = Field(default_factory=list)
    processed_files: dict[int, str] = Field(default_factory=dict)
    meta: dict[int, dict[str, str]] = Field(default_factory=dict)
