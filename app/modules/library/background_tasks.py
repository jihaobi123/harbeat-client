"""Background tasks for automatic audio analysis and stem separation on import.

Both Phase 1 (BPM/key analysis) and Phase 2 (demucs stem separation) run in
child processes so that the heavy libraries (madmom, librosa, torch, demucs)
never bloat the uvicorn worker's resident memory — prevents OOM kills.

Resource safety:
- A Redis-based lock ensures only ONE analysis pipeline runs at a time,
  even across separate processes (API background tasks + batch scripts).
- Child processes have a 1.5 GB RLIMIT_AS memory limit (Linux only).
"""
from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
import time

from app.shared.database import SessionLocal

logger = logging.getLogger(__name__)

# ── Redis lock: cross-process mutex for analysis pipeline ─────────────────

ANALYSIS_LOCK_KEY = "harbeat:analysis_lock"
ANALYSIS_LOCK_TTL = 1800  # auto-expire after 30min (safety net if process dies)


def _acquire_analysis_lock(timeout: int = 86400) -> bool:
    """Acquire a Redis-based cross-process lock. Returns True if acquired."""
    from app.shared.redis import get_redis
    r = get_redis()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # SET NX with TTL — atomic acquire
        if r.set(ANALYSIS_LOCK_KEY, "1", nx=True, ex=ANALYSIS_LOCK_TTL):
            return True
        time.sleep(1)
    return False


def _release_analysis_lock() -> None:
    """Release the Redis-based cross-process lock."""
    from app.shared.redis import get_redis
    r = get_redis()
    r.delete(ANALYSIS_LOCK_KEY)


def _refresh_analysis_lock() -> None:
    """Reset lock TTL (call periodically during long operations)."""
    from app.shared.redis import get_redis
    r = get_redis()
    r.expire(ANALYSIS_LOCK_KEY, ANALYSIS_LOCK_TTL)

# ── Memory limit for child processes (Linux only) ─────────────────────────

_CHILD_MEM_LIMIT_BYTES = int(1.5 * 1024 * 1024 * 1024)  # 1.5 GB


def _get_preexec_fn():
    """Return a preexec_fn that sets RSS memory limit, or None on non-Linux."""
    if platform.system() != "Linux":
        return None
    try:
        import resource as _resource
        def _limit_memory():
            _resource.setrlimit(_resource.RLIMIT_AS, (_CHILD_MEM_LIMIT_BYTES, _CHILD_MEM_LIMIT_BYTES))
        return _limit_memory
    except ImportError:
        return None

# ── Helper: run Phase 1 analysis in a subprocess ──────────────────────────

_ANALYSIS_SCRIPT = os.path.join(os.path.dirname(__file__), "_run_analysis.py")


def _run_analysis_subprocess(file_path: str) -> dict:
    """Run analyze_audio_file() in a child process and return the result dict.

    This keeps madmom/librosa/numpy out of the uvicorn worker's memory.
    Memory is capped at 2.5 GB to prevent OOM-killing the container.
    """
    result = subprocess.run(
        [sys.executable, _ANALYSIS_SCRIPT, file_path],
        capture_output=True,
        text=True,
        timeout=600,  # 10 min max for analysis
        preexec_fn=_get_preexec_fn(),
    )
    if result.returncode != 0:
        err = (result.stderr or "").strip()
        out = (result.stdout or "").strip()
        # returncode -9 = SIGKILL (OOM), -11 = SIGSEGV
        raise RuntimeError(
            f"analysis subprocess exit={result.returncode} "
            f"{'(OOM KILLED)' if result.returncode == -9 else ''} "
            f"stderr={err[-500:] if err else '(empty)'} "
            f"stdout={out[-200:] if out else '(empty)'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"analysis subprocess returned invalid JSON: {e}; stdout={result.stdout[:500]}")


def run_analysis_and_separation(song_id: str) -> None:
    """Run BPM/key analysis + demucs stem separation in background.

    Called automatically after a song is downloaded.
    Uses a global lock to ensure only one heavy analysis runs at a time,
    preventing concurrent child processes from OOM-killing the container.
    """
    acquired = _acquire_analysis_lock(timeout=86400)  # wait up to 24h — songs queue up after batch import
    if not acquired:
        logger.warning("[bg-analysis] timed out waiting for analysis lock for %s, skipping", song_id)
        return
    try:
        _do_analysis_and_separation(song_id)
    finally:
        _release_analysis_lock()


def _do_analysis_and_separation(song_id: str) -> None:
    """Internal: actual analysis logic, must be called while holding _analysis_lock."""
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
                _refresh_analysis_lock()  # reset TTL before long demucs run
                result = subprocess.run(
                    [
                        python_exe, "-m", "demucs",
                        "-n", "htdemucs",
                        "--segment", "7",   # process 7s chunks (htdemucs max ~7.8, uses swap if needed)
                        "-o", stems_base,
                        song.source_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    # NOTE: no preexec_fn — demucs needs >1.5GB virtual address space
                    # NOTE: no check=True — we handle errors below with better logging
                )
                if result.returncode != 0:
                    stderr_tail = (result.stderr or "").strip()[-800:]
                    raise RuntimeError(
                        f"demucs exit={result.returncode} stderr={stderr_tail or '(empty)'}"
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
