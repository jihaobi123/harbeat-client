"""Use cases built on explicit catalog repository ports."""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import CatalogIndex
from .models import ResolvedPlaylistSong
from .ports import CatalogRepository


@dataclass(frozen=True, slots=True)
class PlaylistResolution:
    songs: tuple[ResolvedPlaylistSong, ...]
    unresolved_catalog_song_ids: tuple[int, ...]

    @property
    def complete(self) -> bool:
        return not self.unresolved_catalog_song_ids


@dataclass(slots=True)
class CatalogService:
    repository: CatalogRepository

    def resolve_playlist(self, playlist_id: int) -> PlaylistResolution:
        if playlist_id <= 0:
            raise ValueError("playlist_id must be positive")
        index = CatalogIndex.build(self.repository.list_library_songs())
        playlist = self.repository.get_playlist(playlist_id)
        if playlist.playlist_id != playlist_id:
            raise ValueError("repository returned a different playlist")
        resolved, unresolved = index.resolve_playlist(playlist)
        return PlaylistResolution(tuple(resolved), tuple(unresolved))
