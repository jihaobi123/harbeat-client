"""Demucs process adapter used by the separation domain service."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class DemucsExecutionError(RuntimeError):
    """Raised when the external Demucs process cannot complete successfully."""


class DemucsRunner(Protocol):
    def run(self, source: Path, output_root: Path, model: str, timeout_sec: int) -> None: ...


@dataclass(frozen=True, slots=True)
class SubprocessDemucsRunner:
    interpreter: str = sys.executable
    model_repo: Path | None = None

    def run(self, source: Path, output_root: Path, model: str, timeout_sec: int) -> None:
        command = [
            self.interpreter,
            "-m",
            "demucs",
            "-n",
            model,
            "-o",
            str(output_root),
        ]
        if self.model_repo is not None:
            repository = self.model_repo.resolve()
            if not repository.is_dir():
                raise DemucsExecutionError(f"demucs model repository not found: {repository}")
            command.extend(["--repo", str(repository)])
        command.append(str(source))
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=max(15, int(timeout_sec)),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DemucsExecutionError("demucs timed out") from exc
        except OSError as exc:
            raise DemucsExecutionError(f"demucs could not start: {type(exc).__name__}") from exc

        if process.returncode != 0:
            raise DemucsExecutionError(f"demucs failed with exit code {process.returncode}")
