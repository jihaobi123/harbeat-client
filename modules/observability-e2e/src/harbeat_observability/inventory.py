"""Read-only source inventory with conservative private-data exclusions."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".dart_tool",
        ".git",
        ".gradle",
        ".idea",
        ".venv",
        ".vscode",
        "__pycache__",
        "backups",
        "build",
        "cache",
        "data",
        "database",
        "dist",
        "logs",
        "models",
        "node_modules",
        "reports",
        "tmp",
        "venv",
    }
)

DEFAULT_EXCLUDED_SUFFIXES = frozenset(
    {
        ".apk",
        ".db",
        ".flac",
        ".key",
        ".m4a",
        ".mp3",
        ".onnx",
        ".part",
        ".pem",
        ".pt",
        ".pth",
        ".sqlite",
        ".sqlite3",
        ".wav",
    }
)

DEFAULT_SOURCE_SUFFIXES = frozenset(
    {
        ".css",
        ".dart",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".kt",
        ".md",
        ".py",
        ".service",
        ".sh",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)

SECRET_FILENAMES = frozenset(
    {
        ".env",
        "fluttersharedpreferences.xml",
        "id_ed25519",
        "id_rsa",
        "secrets.json",
    }
)


@dataclass(frozen=True)
class InventoryPolicy:
    excluded_dirs: frozenset[str] = field(default_factory=lambda: DEFAULT_EXCLUDED_DIRS)
    excluded_suffixes: frozenset[str] = field(default_factory=lambda: DEFAULT_EXCLUDED_SUFFIXES)
    included_suffixes: frozenset[str] = field(default_factory=lambda: DEFAULT_SOURCE_SUFFIXES)
    max_file_bytes: int = 16 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def iter_inventory_files(root: Path, policy: InventoryPolicy) -> Iterable[Path]:
    root = root.resolve()
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name.casefold() not in policy.excluded_dirs
        )
        current_path = Path(current)
        for filename in sorted(filenames):
            path = current_path / filename
            folded_name = filename.casefold()
            suffix = path.suffix.casefold()
            if folded_name in SECRET_FILENAMES or folded_name.startswith(".env"):
                continue
            if suffix in policy.excluded_suffixes:
                continue
            if suffix not in policy.included_suffixes:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > policy.max_file_bytes:
                continue
            yield path


def build_inventory(root: Path, policy: InventoryPolicy | None = None) -> dict:
    root = root.resolve()
    policy = policy or InventoryPolicy()
    files = []
    total_bytes = 0
    for path in iter_inventory_files(root, policy):
        size = path.stat().st_size
        total_bytes += size
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": size,
                "sha256": _sha256(path),
            }
        )
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root_label": root.name,
        "git_head": _git_value(root, "rev-parse", "HEAD"),
        "git_branch": _git_value(root, "branch", "--show-current"),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files": files,
        "exclusions": {
            "directories": sorted(policy.excluded_dirs),
            "suffixes": sorted(policy.excluded_suffixes),
            "secret_filenames": sorted(SECRET_FILENAMES),
            "max_file_bytes": policy.max_file_bytes,
        },
    }


def write_inventory(inventory: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

