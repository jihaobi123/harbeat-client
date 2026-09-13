"""Explicit import adapter for pre-device-identity endpoint preferences."""

from __future__ import annotations

from dataclasses import dataclass

from .endpoint import RkEndpoint


@dataclass(frozen=True, slots=True)
class LegacyEndpointCandidate:
    endpoint: str
    verified: bool = False

    @classmethod
    def parse(cls, raw_url: str) -> "LegacyEndpointCandidate":
        return cls(endpoint=RkEndpoint.parse(raw_url).url)

    def profile_store_payload(self, version: int) -> dict[str, object]:
        return {
            "version": version,
            "active_device_id": None,
            "unverified_endpoint": self.endpoint,
            "profiles": [],
        }
