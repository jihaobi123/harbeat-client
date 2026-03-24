from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, HttpUrl


class SongImportItem(BaseModel):
    title: str
    artist: str
    audio_url: HttpUrl
    duration: Optional[float] = None


class PlaylistImportRequest(BaseModel):
    user_id: int
    playlist_name: str
    songs: list[SongImportItem]
    source_type: str = "manual"


class PlaylistImportData(BaseModel):
    playlist_id: int
    import_count: int
    pending_analysis_count: int
