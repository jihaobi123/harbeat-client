"""RQ job functions — each runs in the worker process with its own DB session."""

from __future__ import annotations

import logging
import os
import subprocess
import sys

from app.shared.database import SessionLocal

logger = logging.getLogger(__name__)


def job_analyze(song_id: str) -> dict:
    """Phase 1: BPM / key / energy / beat & cue points.

    Sets analysis_status: queued -> analyzing -> ready|failed
    Does NOT block or require stems.
    """
    db = SessionLocal()
    try:
        from app.modules.library.models import LibrarySong
        from app.modules.library.analysis import analyze_audio_file

        song = db.get(LibrarySong, song_id)
        if not song or not song.source_path or not os.path.isfile(song.source_path):
            return {"ok": False, "error": "song not found or no file", "code": 404}

        # Already analyzed? skip
        if song.analysis_status == "ready":
            return {"ok": True, "skipped": True, "reason": "already analyzed"}

        song.analysis_status = "analyzing"
        db.commit()

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
        song.analysis_status = "ready"
        db.commit()
        logger.info("[job:analyze] analysis ready for %s: BPM=%s Key=%s", song_id, song.bpm, song.key)
        return {"ok": True, "bpm": song.bpm, "key": song.key}
    except Exception:
        logger.exception("[job:analyze] analysis failed for %s", song_id)
        try:
            song.analysis_status = "failed"
            db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


def job_separate_stems(song_id: str) -> dict:
    """Phase 2: demucs stem separation.

    Sets stem_status: none -> queued -> separating -> ready|failed|skipped
    Does NOT set analysis_status (already "ready" from Phase 1).
    """
    db = SessionLocal()
    try:
        from app.modules.library.models import LibrarySong

        song = db.get(LibrarySong, song_id)
        if not song or not song.source_path or not os.path.isfile(song.source_path):
            return {"ok": False, "error": "song not found or no file", "code": 404}

        # Already separated?
        stem_names = ["vocals", "drums", "bass", "other"]
        stems_dir = os.path.join(
            os.path.dirname(os.path.abspath(song.source_path)), "..", "stems", "htdemucs",
            os.path.splitext(os.path.basename(song.source_path))[0],
        )
        stems_dir = os.path.abspath(stems_dir)

        if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
            song.stems = {s: os.path.join(stems_dir, f"{s}.wav") for s in stem_names}
            song.stem_status = "ready"
            db.commit()
            return {"ok": True, "skipped": True, "reason": "stems already exist"}

        song.stem_status = "separating"
        db.commit()

        stems_base = os.path.join(os.path.dirname(os.path.abspath(song.source_path)), "..", "stems")
        stems_base = os.path.abspath(stems_base)
        os.makedirs(stems_base, exist_ok=True)

        python_exe = sys.executable
        logger.info("[job:stems] starting demucs for %s", song_id)
        subprocess.run(
            [
                python_exe, "-m", "demucs",
                "-n", "htdemucs",
                "--segment", "7",
                "-o", stems_base,
                song.source_path,
            ],
            capture_output=True,
            text=True,
            timeout=1800,
            check=True,
        )
        logger.info("[job:stems] demucs finished for %s", song_id)

        if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
            song.stems = {s: os.path.join(stems_dir, f"{s}.wav") for s in stem_names}
            song.stem_status = "ready"
        else:
            song.stem_status = "failed"
        db.commit()
        return {"ok": True, "stem_status": song.stem_status, "stems": song.stems}
    except Exception:
        logger.exception("[job:stems] stem separation failed for %s", song_id)
        try:
            song = db.get(LibrarySong, song_id)
            if song:
                song.stem_status = "failed"
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()
