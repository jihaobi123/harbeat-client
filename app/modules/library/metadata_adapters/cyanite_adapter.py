"""Cyanite adapter placeholder.

Kept disabled unless a future background job implements the vendor call.
"""
from __future__ import annotations

import os

from .base import MetadataAdapter


class CyaniteAdapter(MetadataAdapter):
    source = "cyanite"

    def enabled(self) -> bool:
        return bool(os.getenv("CYANITE_API_KEY", "").strip())

