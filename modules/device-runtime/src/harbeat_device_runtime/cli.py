"""Command line entry point for device-runtime verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__:
  from .probe import probe_runtime
else:
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
  from harbeat_device_runtime.probe import probe_runtime


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("base_url", help="RK edge-agent URL")
  parser.add_argument("--timeout", type=float, default=3.0)
  parser.add_argument("--output", type=Path)
  args = parser.parse_args()
  report = probe_runtime(args.base_url, timeout_sec=args.timeout)
  rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
  if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
  print(rendered)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
