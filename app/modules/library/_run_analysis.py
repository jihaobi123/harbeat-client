#!/usr/bin/env python3
"""Subprocess entry point for audio analysis.

Called by background_tasks.py to run the heavy analysis in an isolated
process, keeping madmom/librosa/numpy out of the uvicorn worker memory.

Usage: python _run_analysis.py <audio_file_path>
Outputs: JSON result dict on stdout.
"""
from __future__ import annotations

import json
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python _run_analysis.py <audio_file_path>", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]

    from app.modules.library.analysis import analyze_audio_file

    result = analyze_audio_file(file_path)

    # Ensure all values are JSON-serializable (numpy types → python types)
    def _convert(obj):
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_convert(v) for v in obj]
        return obj

    json.dump(_convert(result), sys.stdout)


if __name__ == "__main__":
    main()
