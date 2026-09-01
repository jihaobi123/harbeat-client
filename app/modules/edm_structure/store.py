"""Atomic store for shared EDMFormer Shadow sidecars."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Optional, Union

from app.modules.edm_structure.schemas import EdmStructureAnalysisDocument


SAFE_TRACK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class EdmStructureInvalid(ValueError):
    """The EDM sidecar path or payload violates the frozen contract."""


class EdmStructureStore:
    def __init__(self, root: Union[str, Path]):
        self.root = Path(root).expanduser()

    @staticmethod
    def _validate_track_id(track_id: str) -> str:
        if not isinstance(track_id, str) or not SAFE_TRACK_ID.fullmatch(track_id):
            raise EdmStructureInvalid("unsafe EDM structure track_id")
        return track_id

    def _path(self, track_id: str) -> Path:
        return self.root / f"{self._validate_track_id(track_id)}.json"

    def load(self, track_id: str) -> Optional[EdmStructureAnalysisDocument]:
        path = self._path(track_id)
        if not path.exists():
            return None
        try:
            document = EdmStructureAnalysisDocument.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise EdmStructureInvalid(f"EDM sidecar for {track_id} is invalid") from exc
        if document.track_id != track_id:
            raise EdmStructureInvalid("EDM sidecar track_id mismatch")
        return document

    def save(self, document: EdmStructureAnalysisDocument) -> None:
        path = self._path(document.track_id)
        self.root.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(
            document.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n"
        temporary: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.root,
                prefix=f".{document.track_id}.edm-", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        except OSError as exc:
            raise EdmStructureInvalid(
                f"EDM sidecar for {document.track_id} could not be saved"
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

