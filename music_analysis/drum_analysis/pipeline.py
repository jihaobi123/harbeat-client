"""Unified two-branch drum analysis entry point and CLI."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

import soundfile as sf

from .adtof_detector import ADTOFDrumDetector, FPS
from .mdx23c_separator import MDX23CDrumSeparator, TARGET_SAMPLE_RATE
from .schemas import DrumAnalysisResult, string_paths


logger = logging.getLogger(__name__)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def analyze_drums(
    drum_audio_path: str,
    output_dir: str,
    device: str = "auto",
) -> DrumAnalysisResult:
    """Run independent MDX23C separation and ADTOF transcription branches."""
    started = time.perf_counter()
    source = Path(drum_audio_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Drum audio does not exist: {source}")
    destination = Path(output_dir).expanduser().resolve()
    stems_dir = destination / "stems"
    destination.mkdir(parents=True, exist_ok=True)
    stems_dir.mkdir(parents=True, exist_ok=True)

    info = sf.info(source)
    meta: dict[str, Any] = {
        "status": "running",
        "separator": "MDX23C drumsep-6stem",
        "transcriber": "ADTOF-pytorch",
        "requested_device": device,
        "input": str(source),
        "duration_sec": round(float(info.duration), 4),
        "input_sample_rate": int(info.samplerate),
        "sample_rate": TARGET_SAMPLE_RATE,
        "fps": FPS,
        "architecture": {
            "separation_input": "drums.wav",
            "transcription_input": "drums.wav",
            "independent_branches": True,
        },
    }
    try:
        separator = MDX23CDrumSeparator(device=device)
        stems = separator.separate(source, stems_dir)
        detector = ADTOFDrumDetector(device=device)
        transcription = detector.transcribe(source, destination / "drums.mid")
        device_details = {
            "separator": separator.device,
            "transcriber": transcription["device"],
        }

        event_payload = {
            "sample_rate": TARGET_SAMPLE_RATE,
            "fps": FPS,
            "events": transcription["events"],
        }
        _write_json(destination / "drum_events.json", event_payload)
        meta.update(
            {
                "status": "ready",
                "device": (
                    separator.device
                    if separator.device == transcription["device"]
                    else "mixed"
                ),
                "device_details": device_details,
                "processing_time_sec": round(time.perf_counter() - started, 4),
                "thresholds": transcription["thresholds"],
                "event_counts": {
                    name: len(values) for name, values in transcription["events"].items()
                },
            }
        )
        _write_json(destination / "analysis_meta.json", meta)
        return {
            "stems": string_paths(stems),
            "events": transcription["events"],
            "midi_path": str(transcription["midi_path"]),
        }
    except Exception as exc:
        meta.update(
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "processing_time_sec": round(time.perf_counter() - started, 4),
            }
        )
        _write_json(destination / "analysis_meta.json", meta)
        raise


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to Demucs drums.wav")
    parser.add_argument("--output", required=True, help="Output drum_analysis directory")
    parser.add_argument(
        "--device",
        default="auto",
        help="auto, cpu, cuda, cuda:N, or mps",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = analyze_drums(args.input, args.output, args.device)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
