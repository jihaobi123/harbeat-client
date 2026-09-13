#!/usr/bin/env python3
"""Compatibility entry. Implementation: preprocessing/cli/validate_vocal_activity.py."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    runpy.run_module("preprocessing.cli.validate_vocal_activity", run_name="__main__")
else:
    from importlib import import_module
    sys.modules[__name__] = import_module("preprocessing.cli.validate_vocal_activity")
