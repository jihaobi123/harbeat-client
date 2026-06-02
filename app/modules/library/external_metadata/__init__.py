"""External metadata enrichment for dance-style evidence.

This package is used by import/analysis/refresh jobs. DJ Control's live
``/api/dj/styles/pick`` endpoint reads the persisted results only.
"""
from __future__ import annotations

from .service import enrich_song_external_metadata, run_enrich_song_external_metadata

__all__ = ["enrich_song_external_metadata", "run_enrich_song_external_metadata"]

