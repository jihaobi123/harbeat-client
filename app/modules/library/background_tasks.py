"""Background tasks for automatic audio analysis and stem separation on import."""
from __future__ import annotations

import logging
import os
import subprocess
import sys

from app.shared.database import SessionLocal

logger = logging.getLogger(__name__)


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
                from app.modules.library.analysis import analyze_audio_file

                result = analyze_audio_file(song.source_path)
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
                logger.info("[bg-analysis] analysis done for %s: BPM=%s Key=%s", song_id, song.bpm, song.key)
            except Exception:
                logger.exception("[bg-analysis] analysis failed for %s", song_id)
                song.analysis_status = "error"
                db.commit()
            return

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
                        "--segment", "10",   # limit RAM: process 10s chunks instead of full song
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
