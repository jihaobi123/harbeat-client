from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# --- Legacy (still used by practice session) ---
class RecommendationRequest(BaseModel):
    user_id: int
    mode: str
    current_song_id: Optional[int] = None
    target_energy: Optional[str] = None
    source: str = "library"


class RecommendedSongItem(BaseModel):
    song_id: int
    title: str
    artist: str
    in_library: bool = False


class RecommendationData(BaseModel):
    songs: list[RecommendedSongItem]


# --- New discover-style recommendation ---
class DiscoverRequest(BaseModel):
    user_id: int


class DiscoverSongItem(BaseModel):
    song_id: int
    title: str
    artist: str
    style: Optional[str] = None
    energy: Optional[str] = None
    in_library: bool = False


class DiscoverSection(BaseModel):
    key: str
    title: str
    icon: str
    description: str
    songs: list[DiscoverSongItem]


class DiscoverData(BaseModel):
    sections: list[DiscoverSection]


class AddToLibraryRequest(BaseModel):
    user_id: int
    song_id: int


class AddToLibraryData(BaseModel):
    library_song_id: str
    title: str
    artist: str
