"""AIMS adapter placeholder."""
from __future__ import annotations

import os

from .base import MetadataAdapter


class AimsAdapter(MetadataAdapter):
    source = "aims"

    def enabled(self) -> bool:
        return bool(os.getenv("AIMS_API_KEY", "").strip())

