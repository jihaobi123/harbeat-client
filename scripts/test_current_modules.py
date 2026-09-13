#!/usr/bin/env python3
"""Run retained module tests in isolated processes, without deploying anything."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON_MODULES = ("observability-e2e", "device-runtime", "library-catalog",
                  "sequence-planner", "transition-planner", "transition-renderer",
                  "asset-sync", "transition-orchestrator", "audio-runtime", "physical-input")
GROUPS = (*PYTHON_MODULES, "mobile-dj-control", "preprocessing")


def command_for(group: str) -> list[str]:
    if group in PYTHON_MODULES:
        return [sys.executable, "-m", "pytest", "-q", f"modules/{group}/tests"]
    if group == "mobile-dj-control":
        return [shutil.which("dart") or "dart", "run", "modules/mobile-dj-control/tests/mobile_dj_control_test.dart"]
    if group == "preprocessing":
        return [sys.executable, "-m", "pytest", "-q", "tests/test_same_style_preprocess_publisher.py",
                "tests/test_vocal_activity.py", "tests/test_songformer_sections_integration.py",
                "tests/test_analysis_engine_layout.py", "tests/test_current_modules.py",
                "app/tests/test_style_feature_evidence.py"]
    raise ValueError(f"unknown module: {group}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", action="append", choices=GROUPS, help="repeat to select test groups")
    parser.add_argument("--list", action="store_true", help="only list commands")
    parser.add_argument("--stop-on-failure", action="store_true")
    args = parser.parse_args(argv)
    groups = list(dict.fromkeys(args.module or GROUPS))
    failed = []
    for group in groups:
        command = command_for(group)
        print(f"[{group}] {' '.join(command)}", flush=True)
        if args.list:
            continue
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "modules" / group / "src"),
                                                          str(ROOT), env.get("PYTHONPATH")]))
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, timeout=180, check=False)
            passed = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"FAILED: {group}: {exc}", file=sys.stderr, flush=True)
            passed = False
        if not passed:
            failed.append(group)
            if args.stop_on_failure:
                break
    if failed:
        print("Failed groups: " + ", ".join(failed), file=sys.stderr)
        return 1
    if not args.list:
        print(f"All {len(groups)} selected groups passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
