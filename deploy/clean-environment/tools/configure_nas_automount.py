#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path


REQUIRED_OPTIONS = (
    "_netdev",
    "nofail",
    "x-systemd.automount",
    "x-systemd.mount-timeout=60",
)


def update_fstab(text: str, mountpoint: str) -> tuple[str, tuple[str, ...]]:
    output: list[str] = []
    matched = 0
    final_options: tuple[str, ...] = ()
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            output.append(raw)
            continue
        fields = stripped.split()
        if len(fields) < 6 or fields[1] != mountpoint:
            output.append(raw)
            continue
        matched += 1
        options = [item for item in fields[3].split(",") if item]
        for required in REQUIRED_OPTIONS:
            if required not in options:
                options.append(required)
        fields[3] = ",".join(options)
        final_options = tuple(options)
        output.append(" ".join(fields))
    if matched != 1:
        raise ValueError(f"expected exactly one fstab entry for {mountpoint}, found {matched}")
    return "\n".join(output) + "\n", final_options


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fstab", type=Path, default=Path("/etc/fstab"))
    parser.add_argument("--mountpoint", default="/mnt/nas/harbeat")
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    original = args.fstab.read_text(encoding="utf-8")
    updated, options = update_fstab(original, args.mountpoint)
    if args.backup.exists():
        raise SystemExit(f"backup already exists: {args.backup}")
    args.backup.write_text(original, encoding="utf-8")
    os.chmod(args.backup, 0o600)
    temporary = args.fstab.with_name(f".{args.fstab.name}.harbeat.tmp")
    temporary.write_text(updated, encoding="utf-8")
    os.chmod(temporary, args.fstab.stat().st_mode & 0o777)
    temporary.replace(args.fstab)
    print(f"updated {args.mountpoint}: {','.join(options)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
