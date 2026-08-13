"""Explicit identifiers used by Jetson, mobile, and RK."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SongIdentity:
  library_song_id: str
  catalog_song_id: int | None = None

  def __post_init__(self) -> None:
    if not self.library_song_id.strip():
      raise ValueError("library_song_id is required")
    if self.catalog_song_id is not None and self.catalog_song_id <= 0:
      raise ValueError("catalog_song_id must be positive")

  @property
  def playback_asset_id(self) -> str:
    return self.library_song_id
