"""Validated subset of the deployed per-song asset manifest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

STEM_NAMES = ("vocals", "drums", "bass", "other")


class ManifestError(ValueError):
  pass


@dataclass(frozen=True, slots=True)
class AssetFile:
  url: str
  size: int | None
  sha256: str | None
  format: str


@dataclass(frozen=True, slots=True)
class AssetManifest:
  library_song_id: str
  original: AssetFile
  stems: dict[str, AssetFile]
  analysis_status: str

  @classmethod
  def from_api(cls, raw: Mapping[str, Any], expected_library_song_id: str) -> "AssetManifest":
    ids = [raw.get("song_id"), raw.get("library_song_id"), raw.get("songId"), raw.get("librarySongId")]
    present = {str(value) for value in ids if value is not None and str(value)}
    if present != {expected_library_song_id}:
      raise ManifestError(f"manifest identity mismatch: expected {expected_library_song_id}")
    files = raw.get("files")
    if not isinstance(files, Mapping) or not isinstance(files.get("original"), Mapping):
      raise ManifestError("manifest original asset is missing")
    original = _asset_file(files["original"])
    raw_stems = files.get("stems")
    stems = {}
    if isinstance(raw_stems, Mapping):
      unknown = set(raw_stems) - set(STEM_NAMES)
      if unknown:
        raise ManifestError(f"manifest contains unknown stems: {sorted(unknown)}")
      for name in STEM_NAMES:
        if isinstance(raw_stems.get(name), Mapping):
          stems[name] = _asset_file(raw_stems[name])
    return cls(
      library_song_id=expected_library_song_id,
      original=original,
      stems=stems,
      analysis_status=str(raw.get("analysisStatus") or "none"),
    )


def _asset_file(raw: Mapping[str, Any]) -> AssetFile:
  url = str(raw.get("url") or "")
  parsed = urlsplit(url)
  if not url or (parsed.scheme and parsed.scheme not in {"http", "https"}):
    raise ManifestError("asset URL must be relative HTTP path or absolute HTTP URL")
  size = raw.get("size")
  if size is not None and (not isinstance(size, int) or size < 0):
    raise ManifestError("asset size must be a non-negative integer")
  sha = raw.get("sha256")
  if sha is not None and (
    not isinstance(sha, str)
    or len(sha) != 64
    or any(char not in "0123456789abcdefABCDEF" for char in sha)
  ):
    raise ManifestError("asset sha256 must contain 64 hexadecimal characters")
  return AssetFile(url=url, size=size, sha256=sha, format=str(raw.get("format") or ""))
