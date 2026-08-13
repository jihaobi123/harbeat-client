"""Four-stem separation with strict validation and atomic publication."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .analysis import STEM_NAMES
from .runner import DemucsExecutionError, DemucsRunner, SubprocessDemucsRunner


class StemSeparationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StemSeparator:
    model: str = "htdemucs"
    timeout_sec: int = 120
    runner: DemucsRunner | None = None

    def separate(self, audio_path: str, output_root: str) -> dict[str, str]:
        source = Path(audio_path)
        if not source.is_file():
            raise StemSeparationError(f"audio file not found: {audio_path}")

        root = Path(output_root).resolve()
        canonical = root / self.model / source.stem
        existing = complete_stem_paths(canonical)
        if existing:
            return existing

        root.mkdir(parents=True, exist_ok=True)
        self._invoke(source, root)
        result = complete_stem_paths(canonical)
        if result:
            return result

        result = self._separate_through_safe_input(source, root, canonical)
        if not result:
            raise StemSeparationError("demucs completed without all four stem files")
        return result

    def _invoke(self, source: Path, root: Path) -> None:
        runner = self.runner or SubprocessDemucsRunner()
        try:
            runner.run(source, root, self.model, self.timeout_sec)
        except DemucsExecutionError as exc:
            raise StemSeparationError(str(exc)) from exc

    def _separate_through_safe_input(
        self,
        source: Path,
        root: Path,
        canonical: Path,
    ) -> dict[str, str] | None:
        safe_source = _safe_input_path(source, root)
        safe_source.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source, safe_source)
            self._invoke(safe_source, root)
            safe_result = complete_stem_paths(root / self.model / safe_source.stem)
            if not safe_result:
                return None
            return _publish_stems(safe_result, canonical)
        finally:
            safe_source.unlink(missing_ok=True)


def complete_stem_paths(directory: Path) -> dict[str, str] | None:
    result = {name: str(directory / f"{name}.wav") for name in STEM_NAMES}
    complete = all(Path(path).is_file() and Path(path).stat().st_size > 0 for path in result.values())
    return result if complete else None


def separation_result(
    status: str,
    stems: Mapping[str, str] | None = None,
    error: str | None = None,
) -> dict[str, object]:
    normalized = dict(stems or {})
    complete = set(normalized) == set(STEM_NAMES) and all(normalized.values())
    return {
        "status": status if complete else "failed",
        "model": "htdemucs",
        "stems": normalized,
        "complete": complete,
        "error": error,
    }


def _safe_input_path(source: Path, root: Path) -> Path:
    digest = hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()[:16]
    suffix = source.suffix or ".wav"
    return root / "_inputs" / f"source_{digest}{suffix}"


def _publish_stems(stems: Mapping[str, str], canonical: Path) -> dict[str, str] | None:
    canonical.mkdir(parents=True, exist_ok=True)
    for name in STEM_NAMES:
        source = Path(stems[name])
        destination = canonical / f"{name}.wav"
        temporary = destination.with_suffix(".wav.part")
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
    return complete_stem_paths(canonical)
