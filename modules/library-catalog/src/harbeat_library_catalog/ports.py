"""External data ports for the library catalog domain."""

from __future__ import annotations

from typing import Protocol

from .models import LibrarySong, Playlist


class CatalogRepository(Protocol):
    def list_library_songs(self) -> list[LibrarySong]: ...

    def get_playlist(self, playlist_id: int) -> Playlist: ...
