"""Application service separating analysis from catalog persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from .dj_structure_v2 import VERSION
from .version_gate import validate_dj_structure_v2


class AnalysisRepository(Protocol):
    def load_features(self, song_id: str) -> Mapping[str, Any]: ...

    def save_features(self, song_id: str, features: Mapping[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class PreprocessResult:
    song_id: str
    payload: Mapping[str, Any]
    reused: bool


@dataclass(slots=True)
class PreprocessService:
    repository: AnalysisRepository
    analyzer: Callable[[str], Mapping[str, Any]]

    def process(self, song_id: str, *, force: bool = False) -> PreprocessResult:
        if not song_id.strip():
            raise ValueError("song_id is required")
        features = dict(self.repository.load_features(song_id) or {})
        existing = features.get(VERSION)
        if isinstance(existing, Mapping) and not force:
            validate_dj_structure_v2(existing)
            return PreprocessResult(song_id, existing, reused=True)

        payload = dict(self.analyzer(song_id))
        validate_dj_structure_v2(payload)
        features[VERSION] = payload
        self.repository.save_features(song_id, features)
        return PreprocessResult(song_id, payload, reused=False)
