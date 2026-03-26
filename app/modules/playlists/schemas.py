from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, HttpUrl


class SongImportItem(BaseModel):
    title: str
    artist: str
    audio_url: Optional[HttpUrl] = None
    duration: Optional[float] = None
    bpm: Optional[int] = None
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
