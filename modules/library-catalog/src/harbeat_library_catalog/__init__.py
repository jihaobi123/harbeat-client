"""Library, playlist, and manifest contracts."""

from .catalog import CatalogIndex, CatalogMappingError
from .identity import SongIdentity
from .manifest import AssetManifest, ManifestError
from .models import LibrarySong, Playlist, PlaylistSong, ResolvedPlaylistSong
from .ports import CatalogRepository
from .service import CatalogService, PlaylistResolution

__all__ = [
  "AssetManifest",
  "CatalogIndex",
  "CatalogMappingError",
  "CatalogRepository",
  "CatalogService",
  "LibrarySong",
  "ManifestError",
  "Playlist",
  "PlaylistSong",
  "PlaylistResolution",
  "ResolvedPlaylistSong",
  "SongIdentity",
]
