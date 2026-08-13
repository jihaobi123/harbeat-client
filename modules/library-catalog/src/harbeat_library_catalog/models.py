"""Small catalog DTOs independent from SQLAlchemy and Flutter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .identity import SongIdentity


def _positive_int(value: Any) -> int | None:
  if isinstance(value, bool):
    return None
  try:
    result = int(value)
  except (TypeError, ValueError):
    return None
  return result if result > 0 else None


@dataclass(frozen=True, slots=True)
class LibrarySong:
  identity: SongIdentity
  title: str
  artist: str
  duration_sec: float = 0.0
  analysis_status: str = "none"

  @classmethod
  def from_api(cls, raw: Mapping[str, Any]) -> "LibrarySong":
    library_id = raw.get("id")
    if not isinstance(library_id, str) or not library_id.strip():
      raise ValueError("library song response is missing string id")
    return cls(
      identity=SongIdentity(library_id, _positive_int(raw.get("song_id"))),
      title=str(raw.get("title") or ""),
      artist=str(raw.get("artist") or ""),
      duration_sec=max(0.0, float(raw.get("duration") or 0.0)),
      analysis_status=str(raw.get("analysis_status") or "none"),
    )


@dataclass(frozen=True, slots=True)
class PlaylistSong:
  catalog_song_id: int
  title: str
  artist: str
  order_index: int

  @classmethod
  def from_api(cls, raw: Mapping[str, Any]) -> "PlaylistSong":
    song_id = _positive_int(raw.get("song_id"))
    if song_id is None:
      raise ValueError("playlist song response is missing positive catalog song_id")
    return cls(
      catalog_song_id=song_id,
      title=str(raw.get("title") or ""),
      artist=str(raw.get("artist") or ""),
      order_index=max(0, int(raw.get("order_index") or 0)),
    )


@dataclass(frozen=True, slots=True)
class Playlist:
  playlist_id: int
  name: str
  songs: tuple[PlaylistSong, ...]

  @classmethod
  def from_api(cls, raw: Mapping[str, Any]) -> "Playlist":
    playlist_id = _positive_int(raw.get("id"))
    if playlist_id is None:
      raise ValueError("playlist response is missing positive id")
    rows = raw.get("songs") or []
    if not isinstance(rows, list):
      raise ValueError("playlist songs must be an array")
    songs = tuple(sorted((PlaylistSong.from_api(row) for row in rows), key=lambda item: item.order_index))
    return cls(playlist_id, str(raw.get("playlist_name") or ""), songs)


@dataclass(frozen=True, slots=True)
class ResolvedPlaylistSong:
  playlist_id: int
  order_index: int
  identity: SongIdentity
  title: str
  artist: str
