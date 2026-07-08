"""Bridge.audio adapter placeholder."""
from __future__ import annotations

import os

from .base import MetadataAdapter


class BridgeAdapter(MetadataAdapter):
    source = "bridge"

    def enabled(self) -> bool:
        return bool(os.getenv("BRIDGE_API_KEY", "").strip())

