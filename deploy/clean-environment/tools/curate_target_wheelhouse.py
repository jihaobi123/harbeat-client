#!/usr/bin/env python3
"""Copy only wheels matching a validated target environment freeze."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, parse_wheel_filename


def load_freeze(path: Path) -> dict[str, str]:
    locked: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" in line:
            name, version = line.split("==", 1)
            locked[canonicalize_name(name)] = version
            continue
        requirement = Requirement(line)
        if not requirement.url:
            continue
        filename = Path(unquote(urlparse(requirement.url).path)).name
        _name, version, _build, _tags = parse_wheel_filename(filename)
        locked[canonicalize_name(requirement.name)] = str(version)
    return locked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()

    locked = load_freeze(args.freeze)
    args.target.mkdir(parents=True, exist_ok=True)
    selected: dict[str, Path] = {}
    for wheel in sorted(args.source.glob("*.whl")):
        try:
            name, version, _build, _tags = parse_wheel_filename(wheel.name)
        except ValueError:
            continue
        normalized = canonicalize_name(name)
        if str(version) == locked.get(normalized):
            selected[normalized] = wheel

    missing = sorted(
        name for name in set(locked) - set(selected) - {"pip", "setuptools"}
        if not name.startswith("harbeat-")
    )
    if missing:
        raise SystemExit(f"validated wheels missing: {', '.join(missing)}")
    for source in selected.values():
        shutil.copy2(source, args.target / source.name)
    print(f"curated wheels: {len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
