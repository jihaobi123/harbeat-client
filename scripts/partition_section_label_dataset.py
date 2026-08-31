#!/usr/bin/env python3
"""Create stable whole-track partitions for the shared annotation workbench."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.section_annotation_partitions import (
    ensure_annotation_partition,
    partition_summary,
)
from app.modules.library.section_relabel_dataset import validate_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--partition-count", type=int, default=2)
    parser.add_argument("--replace-existing-if-unreviewed", action="store_true")
    return parser.parse_args()


def atomic_write(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as destination:
        json.dump(payload, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    path = args.dataset.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    previous_summary = partition_summary(payload)
    if payload.get("annotation_partition") is not None and args.replace_existing_if_unreviewed:
        if previous_summary["global"]["reviewed_segments"]:
            raise SystemExit("refusing to repartition after annotation has started")
        payload.pop("annotation_partition")
    changed = ensure_annotation_partition(
        payload, partition_count=args.partition_count
    )
    payload["validation_summary"] = validate_dataset(payload, require_audio=True)
    if changed:
        backup = path.with_name(f"{path.stem}.before_partition{path.suffix}")
        shutil.copy2(path, backup)
        atomic_write(path, payload)
    print(
        json.dumps(
            {
                "status": "created" if changed else "unchanged",
                "dataset": str(path),
                **partition_summary(payload),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
