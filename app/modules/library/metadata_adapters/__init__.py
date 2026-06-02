"""Optional external metadata adapters for cached genre/style evidence.

Adapters are used by import/analysis/refresh jobs, not by the live
``/api/dj/styles/pick`` request path.
"""
from __future__ import annotations

from .base import MetadataAdapter, MetadataTagEvidence
from .discogs_adapter import DiscogsAdapter
from .lastfm_adapter import LastfmAdapter
from .musicbrainz_adapter import MusicBrainzAdapter
from .cyanite_adapter import CyaniteAdapter
from .bridge_adapter import BridgeAdapter
from .aims_adapter import AimsAdapter

__all__ = [
    "MetadataAdapter",
    "MetadataTagEvidence",
    "DiscogsAdapter",
    "LastfmAdapter",
    "MusicBrainzAdapter",
    "CyaniteAdapter",
    "BridgeAdapter",
    "AimsAdapter",
]

