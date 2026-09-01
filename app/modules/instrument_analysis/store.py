"""Atomic storage for shared instrument-analysis model candidates."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Optional, Union

from app.modules.instrument_analysis.schemas import InstrumentAnalysisDocument


SAFE_TRACK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class InstrumentAnalysisInvalid(ValueError):
    """A sidecar path or payload violates the frozen contract."""


class InstrumentAnalysisStore:
    def __init__(self, root: Union[str, Path]):
        self.root = Path(root).expanduser()

    @staticmethod
    def _validate_track_id(track_id: str) -> str:
        if not isinstance(track_id, str) or not SAFE_TRACK_ID.fullmatch(track_id):
            raise InstrumentAnalysisInvalid("unsafe instrument-analysis track_id")
        return track_id

    def _path(self, track_id: str) -> Path:
        return self.root / f"{self._validate_track_id(track_id)}.json"

    def load(self, track_id: str) -> Optional[InstrumentAnalysisDocument]:
        path = self._path(track_id)
        if not path.exists():
            return None
        try:
            document = InstrumentAnalysisDocument.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise InstrumentAnalysisInvalid(
                f"instrument-analysis sidecar for {track_id} is invalid"
            ) from exc
        if document.track_id != track_id:
            raise InstrumentAnalysisInvalid("instrument-analysis track_id mismatch")
        return document

    def save(self, document: InstrumentAnalysisDocument) -> None:
        path = self._path(document.track_id)
        self.root.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(
            document.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f".{document.track_id}.instrument-",
                suffix=".tmp",
                dir=self.root,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        except OSError as exc:
            raise InstrumentAnalysisInvalid(
                f"instrument-analysis sidecar for {document.track_id} could not be saved"
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
