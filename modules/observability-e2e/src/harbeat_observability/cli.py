"""Command line interface for safe inventory and semantic UI inspection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harbeat_observability.android import AndroidDevice
from harbeat_observability.inventory import build_inventory, write_inventory
from harbeat_observability.journal import endpoint_counts, parse_http_events
from harbeat_observability.ui_semantics import find_control, parse_controls


def _inventory(args: argparse.Namespace) -> int:
    inventory = build_inventory(args.root)
    write_inventory(inventory, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_count": inventory["file_count"],
                "total_bytes": inventory["total_bytes"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def _find_control(args: argparse.Namespace) -> int:
    control = find_control(
        parse_controls(args.xml),
        args.label,
        resource_id=args.resource_id,
        exact=not args.contains,
    )
    if control is None:
        print(json.dumps({"found": False, "label": args.label}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "found": True,
                "label": control.label,
                "resource_id": control.resource_id,
                "bounds": control.bounds,
                "center": control.center,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _find_android_control(args: argparse.Namespace) -> int:
    control = AndroidDevice(args.serial).find_fresh_control(
        args.label,
        resource_id=args.resource_id,
        exact=not args.contains,
    )
    if control is None:
        print(json.dumps({"found": False, "label": args.label}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "found": True,
                "label": control.label,
                "resource_id": control.resource_id,
                "bounds": control.bounds,
                "center": control.center,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _summarize_journal(args: argparse.Namespace) -> int:
    lines = args.input.read_text(encoding="utf-8", errors="replace").splitlines()
    events = parse_http_events(lines, source=args.source)
    print(
        json.dumps(
            {"event_count": len(events), "endpoints": endpoint_counts(events)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    inventory = commands.add_parser("inventory")
    inventory.add_argument("--root", type=Path, required=True)
    inventory.add_argument("--output", type=Path, required=True)
    inventory.set_defaults(handler=_inventory)

    find = commands.add_parser("find-control")
    find.add_argument("--xml", type=Path, required=True)
    find.add_argument("--label", required=True)
    find.add_argument("--resource-id")
    find.add_argument("--contains", action="store_true")
    find.set_defaults(handler=_find_control)

    android = commands.add_parser("find-android-control")
    android.add_argument("--serial", required=True)
    android.add_argument("--label", required=True)
    android.add_argument("--resource-id")
    android.add_argument("--contains", action="store_true")
    android.set_defaults(handler=_find_android_control)

    journal = commands.add_parser("summarize-journal")
    journal.add_argument("--input", type=Path, required=True)
    journal.add_argument("--source", required=True)
    journal.set_defaults(handler=_summarize_journal)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
