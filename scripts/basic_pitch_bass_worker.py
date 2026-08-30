#!/usr/bin/env python3
"""Optional Basic Pitch worker implementing Harbeat's JSON model contract."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from importlib import metadata
import io
import json
from pathlib import Path


def _bend_values(raw) -> list[float]:
    if raw is None:
        return []
    values = []
    for item in raw:
        value = item[-1] if isinstance(item, (list, tuple)) else item
        try:
            values.append(round(float(value), 4))
        except (TypeError, ValueError):
            continue
    return values[:256]


def transcribe(audio_path: Path) -> dict:
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict
    except ImportError as exc:
        raise RuntimeError(
            "basic-pitch is not installed; install it only in the optional model environment"
        ) from exc

    # Basic Pitch prints progress and backend tensor diagnostics to stdout.
    # The model-adapter contract requires stdout to contain exactly one JSON
    # document, so keep all upstream chatter out of the transport channel.
    with redirect_stdout(io.StringIO()):
        _, _, note_events = predict(str(audio_path))
    events = []
    for value in note_events:
        if len(value) < 4:
            continue
        start, end, midi, amplitude = value[:4]
        events.append({
            "start": round(float(start), 4),
            "end": round(float(end), 4),
            "midi": round(float(midi), 4),
            "confidence": round(float(amplitude), 4),
            "pitch_bends": _bend_values(value[4] if len(value) >= 5 else None),
        })
    events.sort(key=lambda item: (item["start"], item["midi"], item["end"]))
    return {
        "engine": "spotify_basic_pitch",
        "model_name": Path(str(ICASSP_2022_MODEL_PATH)).name,
        "model_version": metadata.version("basic-pitch"),
        "license": "Apache-2.0",
        "event_count": len(events),
        "note_events": events,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(transcribe(args.audio), ensure_ascii=False))


if __name__ == "__main__":
    main()
