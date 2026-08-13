"""Deterministic catalog indexes and playlist resolution."""

from __future__ import annotations

from dataclasses import dataclass

from .models import LibrarySong, Playlist, ResolvedPlaylistSong


class CatalogMappingError(ValueError):
  pass


@dataclass(frozen=True, slots=True)
class CatalogIndex:
  by_library_id: dict[str, LibrarySong]
  by_catalog_id: dict[int, LibrarySong]

  @classmethod
  def build(cls, songs: list[LibrarySong]) -> "CatalogIndex":
    by_library: dict[str, LibrarySong] = {}
    by_catalog: dict[int, LibrarySong] = {}
    for song in songs:
      library_id = song.identity.library_song_id
      if library_id in by_library:
        raise CatalogMappingError(f"duplicate library_song_id: {library_id}")
      by_library[library_id] = song
      catalog_id = song.identity.catalog_song_id
      if catalog_id is not None:
        if catalog_id in by_catalog:
          raise CatalogMappingError(f"ambiguous catalog_song_id: {catalog_id}")
        by_catalog[catalog_id] = song
    return cls(by_library, by_catalog)

  def resolve_playlist(self, playlist: Playlist) -> tuple[list[ResolvedPlaylistSong], list[int]]:
    resolved = []
    unresolved = []
    for row in playlist.songs:
      song = self.by_catalog_id.get(row.catalog_song_id)
      if song is None:
        unresolved.append(row.catalog_song_id)
        continue
      resolved.append(ResolvedPlaylistSong(
        playlist_id=playlist.playlist_id,
        order_index=row.order_index,
        identity=song.identity,
        title=song.title,
        artist=song.artist,
      ))
    return resolved, unresolved
