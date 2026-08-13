"""Behavior-compatible htdemucs runner with strict output validation."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .analysis import STEM_NAMES


class StemSeparationError(RuntimeError):
  pass


@dataclass(frozen=True, slots=True)
class StemSeparator:
  model: str = "htdemucs"
  timeout_sec: int = 120

  def separate(self, audio_path: str, output_root: str) -> dict[str, str]:
    source = Path(audio_path)
    if not source.is_file():
      raise StemSeparationError(f"audio file not found: {audio_path}")
    root = Path(output_root).resolve()
    canonical = root / self.model / source.stem
    existing = _complete(canonical)
    if existing:
      return existing
    root.mkdir(parents=True, exist_ok=True)
    self._invoke(source, root)
    result = _complete(canonical)
    if result:
      return result
    safe = f"src_{hashlib.sha1(str(source).encode('utf-8', errors='ignore')).hexdigest()[:16]}{source.suffix or '.wav'}"
    safe_dir = root / "_inputs"
    safe_dir.mkdir(parents=True, exist_ok=True)
    safe_source = safe_dir / safe
    try:
      shutil.copyfile(source, safe_source)
      self._invoke(safe_source, root)
      safe_result = _complete(root / self.model / safe_source.stem)
      if safe_result:
        canonical.mkdir(parents=True, exist_ok=True)
        for name, path in safe_result.items():
          destination = canonical / f"{name}.wav"
          shutil.copyfile(path, destination)
        result = _complete(canonical)
    finally:
      try:
        safe_source.unlink()
      except OSError:
        pass
    if not result:
      raise StemSeparationError("demucs completed without all four stem files")
    return result

  def _invoke(self, source: Path, root: Path) -> None:
    try:
      process = subprocess.run([sys.executable, "-m", "demucs", "-n", self.model, "-o", str(root), str(source)], capture_output=True, text=True, timeout=max(15, int(self.timeout_sec)), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
      raise StemSeparationError(f"demucs invocation failed: {type(exc).__name__}") from exc
    if process.returncode != 0:
      raise StemSeparationError(f"demucs failed with exit code {process.returncode}")


def _complete(directory: Path) -> dict[str, str] | None:
  result = {name: str(directory / f"{name}.wav") for name in STEM_NAMES}
  return result if all(Path(path).is_file() and Path(path).stat().st_size > 0 for path in result.values()) else None


def separation_result(status: str, stems: dict[str, str] | None = None, error: str | None = None) -> dict[str, object]:
  complete = bool(stems and set(stems) == set(STEM_NAMES))
  return {"status": status if complete else "failed", "model": "htdemucs", "stems": stems or {}, "complete": complete, "error": error}
