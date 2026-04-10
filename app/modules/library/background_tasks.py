"""Background tasks for automatic audio analysis and stem separation on import.

Both Phase 1 (BPM/key analysis) and Phase 2 (demucs stem separation) run in
child processes so that the heavy libraries (madmom, librosa, torch, demucs)
never bloat the uvicorn worker's resident memory — prevents OOM kills.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys

from app.shared.database import SessionLocal

logger = logging.getLogger(__name__)

# ── Helper: run Phase 1 analysis in a subprocess ──────────────────────────

_ANALYSIS_SCRIPT = os.path.join(os.path.dirname(__file__), "_run_analysis.py")


def _run_analysis_subprocess(file_path: str) -> dict:
    """Run analyze_audio_file() in a child process and return the result dict.

    This keeps madmom/librosa/numpy out of the uvicorn worker's memory.
    """
    result = subprocess.run(
        [sys.executable, _ANALYSIS_SCRIPT, file_path],
        capture_output=True,
        text=True,
        timeout=600,  # 10 min max for analysis
    )
    if result.returncode != 0:
        raise RuntimeError(f"analysis subprocess failed: {result.stderr[-1000:]}")
    return json.loads(result.stdout)


def run_analysis_and_separation(song_id: str) -> None:
    """Run BPM/key analysis + demucs stem separation in background.

    Called automatically after a song is downloaded.
    Creates its own DB session since this runs outside the request lifecycle.
    """
    db = SessionLocal()
    try:
        from app.modules.library.models import LibrarySong

        song = db.get(LibrarySong, song_id)
        if not song or not song.source_path or not os.path.isfile(song.source_path):
            logger.warning("[bg-analysis] song %s not found or no file", song_id)
            return

        # --- Phase 1: BPM / Key / Energy / Beat & Cue points ---
        # Skip if already analyzed (e.g. retrying after interrupted stem separation)
        if song.bpm is not None and song.key is not None:
            logger.info("[bg-analysis] skipping Phase 1 for %s (already has BPM=%s Key=%s)", song_id, song.bpm, song.key)
        else:
            song.analysis_status = "analyzing"
            db.commit()

            try:
                logger.info("[bg-analysis] starting Phase 1 analysis (subprocess) for %s", song_id)
                result = _run_analysis_subprocess(song.source_path)
                song.bpm = result["bpm"]
                song.duration = result["duration"]
                song.key = result.get("key")
                song.camelot_key = result.get("camelot_key")
                song.energy = result.get("energy")
                song.beat_points = result.get("beat_points", [])
                song.downbeats = result.get("downbeats", [])
                song.phrase_map = result.get("phrase_map", [])
                song.key_confidence = result.get("key_confidence")
                raw_cues = result.get("cue_points", [])
                song.cue_points = [
                    {"id": f"cue-{song_id}-{i}", "time": c["time"], "label": c["label"], "color": c["color"]}
                    for i, c in enumerate(raw_cues)
                ]
                db.commit()
                logger.info("[bg-analysis] Phase 1 done for %s: BPM=%s Key=%s", song_id, song.bpm, song.key)
            except Exception:
                logger.exception("[bg-analysis] Phase 1 failed for %s", song_id)
                song.analysis_status = "error"
                db.commit()

        # --- Phase 2: Stem separation (demucs) ---
        try:
            stems_base = os.path.join(os.path.dirname(os.path.abspath(song.source_path)), "..", "stems")
            stems_base = os.path.abspath(stems_base)
            os.makedirs(stems_base, exist_ok=True)

            base_name = os.path.splitext(os.path.basename(song.source_path))[0]
            stems_dir = os.path.join(stems_base, "htdemucs", base_name)
            stem_names = ["vocals", "drums", "bass", "other"]

            # Skip if already separated
            if not all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
                python_exe = sys.executable
                logger.info("[bg-analysis] starting demucs for %s", song_id)
                result = subprocess.run(
                    [
                        python_exe, "-m", "demucs",
                        "-n", "htdemucs",
                        "--segment", "7",   # limit RAM: process 7s chunks (htdemucs max ~7.8)
                        "-o", stems_base,
                        song.source_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    check=True,
                )
                logger.info("[bg-analysis] demucs finished for %s", song_id)

            if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
                song.stems = {s: os.path.join(stems_dir, f"{s}.wav") for s in stem_names}
                logger.info("[bg-analysis] stems separated for %s", song_id)
            else:
                logger.warning("[bg-analysis] stem files not found after demucs for %s", song_id)
        except Exception:
            logger.exception("[bg-analysis] stem separation failed for %s (non-fatal)", song_id)

        # Mark completed regardless of stem separation outcome
        song.analysis_status = "completed"
        db.commit()
    except Exception:
        logger.exception("[bg-analysis] unexpected error for %s", song_id)
    finally:
        db.close()


def copy_analysis_from(source: object, target: object) -> None:
    """Copy analysis results from an existing LibrarySong to a new one."""
    for field in ("bpm", "duration", "key", "camelot_key", "energy",
                  "beat_points", "downbeats", "phrase_map", "key_confidence",
                  "cue_points", "stems", "analysis_status"):
        val = getattr(source, field, None)
        if val is not None:
            setattr(target, field, val)
