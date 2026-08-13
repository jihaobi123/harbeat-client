"""Pure cache validation and atomic publication for RK assets."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class AssetSpec:
    sha256: str | None = None
    size: int | None = None

    def __post_init__(self) -> None:
        if self.size is not None and self.size < 0:
            raise ValueError("asset size must be non-negative")
        if self.sha256 is not None and (
            len(self.sha256) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in self.sha256)
        ):
            raise ValueError("asset sha256 must contain 64 hexadecimal characters")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def validate_cached_asset(path: Path, spec: AssetSpec, *, verify_full: bool = False) -> bool:
    if not path.is_file():
        return False
    stat = path.stat()
    if verify_full and spec.sha256:
        return sha256_file(path) == spec.sha256.lower()

    metadata = _read_sidecar(sidecar_path(path))
    if metadata and _sidecar_matches_file(metadata, stat.st_size, stat.st_mtime_ns):
        recorded_sha = metadata.get("sha256")
        converted_sha = metadata.get("converted_from_sha256")
        if spec.sha256 and spec.sha256 not in {recorded_sha, converted_sha}:
            return False
        converted_size = metadata.get("converted_from_size")
        if spec.size is not None and converted_size is not None:
            return int(converted_size) == spec.size
        if spec.sha256:
            return True

    if spec.size is not None and stat.st_size != spec.size:
        return False
    return not spec.sha256 or sha256_file(path) == spec.sha256.lower()


def verify_download(path: Path, spec: AssetSpec) -> None:
    if not path.is_file():
        raise ValueError("downloaded asset is missing")
    if spec.size is not None and path.stat().st_size != spec.size:
        raise ValueError(f"asset size mismatch: got {path.stat().st_size}, want {spec.size}")
    if spec.sha256 and sha256_file(path) != spec.sha256.lower():
        raise ValueError("asset sha256 mismatch")


def atomic_publish(temporary: Path, destination: Path) -> Path:
    if not temporary.is_file():
        raise ValueError("temporary asset is missing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("r+b") as source:
        os.fsync(source.fileno())
    os.replace(temporary, destination)
    return destination


def _read_sidecar(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8").strip())
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, Mapping) else {}


def _sidecar_matches_file(metadata: Mapping[str, object], size: int, mtime_ns: int) -> bool:
    recorded_size = metadata.get("size")
    recorded_mtime = metadata.get("mtime_ns")
    return (
        (recorded_size is None or int(recorded_size) == size)
        and (recorded_mtime is None or int(recorded_mtime) == mtime_ns)
    )
