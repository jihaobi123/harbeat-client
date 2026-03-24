from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RecommendationRequest(BaseModel):
    user_id: int
    mode: str
    current_song_id: Optional[int] = None
    target_energy: Optional[str] = None


class RecommendedSongItem(BaseModel):
    song_id: int
    title: str
    artist: str


class RecommendationData(BaseModel):
    songs: list[RecommendedSongItem]
