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


# --- Vibe / semantic search ---
class VibeSearchRequest(BaseModel):
    query: str
    user_id: Optional[int] = None
    top_k: int = 12


class VibeSearchSongItem(BaseModel):
    song_id: int
    title: str
    artist: str
    style: Optional[str] = None
    energy: Optional[str] = None
    distance: float = 0.0
    in_library: bool = False
    library_song_id: Optional[str] = None


class VibeSearchData(BaseModel):
    query: str
    vibe_description: str
    genres: list[str]
    songs: list[VibeSearchSongItem]


class ReindexData(BaseModel):
    indexed_count: int


class ReindexClapData(BaseModel):
    success: int
    failed: int
    total: int


class VectorStoreStatsData(BaseModel):
    collection: str
    count: int
    text_count: int = 0
