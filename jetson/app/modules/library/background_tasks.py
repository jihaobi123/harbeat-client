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

import gc
import json
import logging
import os
import platform
import subprocess
import sys
import time

from app.shared.database import SessionLocal

logger = logging.getLogger(__name__)


def apply_stem_analysis(song) -> None:
    """Persist planner-ready analysis for already separated stem files."""
    from app.modules.library.stem_analysis import analyze_stem_files

    result = analyze_stem_files(song.stems, original_path=song.source_path)
    song.stem_activity = result["stem_activity"]
    song.stem_activity_windows = result["stem_activity_windows"]
    song.stem_quality_score = result["stem_quality_score"]
    song.intro_is_clean = result["intro_is_clean"]
    song.outro_is_clean = result["outro_is_clean"]
    song.has_drum_loop = result["has_drum_loop"]


def apply_dj_fingerprint(db, song) -> None:
    """Persist explainable DJ fingerprint features and ranked dance styles."""
    from app.modules.dj_control.dance_style import STYLE_PROFILES, score_song_combined
    from app.modules.library.dj_feature_extractor import extract_dj_features

    features = extract_dj_features(song)
    music_features = dict(getattr(song, "music_features", {}) or {})
    music_features["dj"] = features
    song.music_features = music_features

    ranked = []
    scores = {}
    for style_key in STYLE_PROFILES:
        score, source, breakdown = score_song_combined(song, style_key)
        scores[style_key] = round(score, 4)
        ranked.append({
            "style": style_key,
            "score": round(score, 4),
            "source": source,
            "breakdown": breakdown,
        })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    song.dance_styles = ranked
    song.dance_style_scores = scores
    song.dance_style_status = "ready"
    db.add(song)
    db.commit()

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

# ── Memory management ─────────────────────────────────────────────────────

def _force_memory_release():
    """Force glibc to return freed memory to OS.

    Python's gc.collect() frees Python objects, but glibc's malloc keeps
    freed pages in its arena for reuse.  malloc_trim(0) forces glibc to
    release those pages back to the kernel, preventing RSS from growing
    monotonically across multiple songs.
    """
    gc.collect()
    if platform.system() == "Linux":
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
        except Exception:
            pass


# ── Memory limit for child processes (Linux only) ─────────────────────────

_CHILD_MEM_LIMIT_BYTES = int(2.5 * 1024 * 1024 * 1024)  # 2.5 GB


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
        _force_memory_release()  # return freed pages to OS after each song


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
                song.bpm_curve = result.get("bpm_curve", [])
                song.tempo_stability = result.get("tempo_stability")
                song.energy_curve = result.get("energy_curve", [])
                song.loudness_profile = result.get("loudness_profile", {})
                song.transition_windows = result.get("transition_windows", [])
                song.downbeats = result.get("downbeats", [])
                song.phrase_map = result.get("phrase_map", [])
                song.key_confidence = result.get("key_confidence")
                song.beat_confidence = result.get("beat_confidence")
                song.beat_grid_offset = result.get("beat_grid_offset")
                song.beat_grid_interval = result.get("beat_grid_interval")
                song.beat_engines_used = result.get("beat_engines_used", [])
                song.beat_needs_review = int(result.get("beat_needs_review", False))
                raw_cues = result.get("cue_points", [])
                song.cue_points = [
                    {"id": f"cue-{song_id}-{i}", "time": c["time"], "label": c["label"], "color": c["color"]}
                    for i, c in enumerate(raw_cues)
                ]
                # Phase 1 produced bpm/key/energy AND beats/downbeats → mark beats_done
                song.analysis_stage = "beats_done"
                db.commit()
                logger.info("[bg-analysis] Phase 1 done for %s: BPM=%s Key=%s", song_id, song.bpm, song.key)
            except Exception as _e:
                logger.exception("[bg-analysis] Phase 1 failed for %s", song_id)
                song.analysis_status = "error"
                song.analysis_error = f"phase1: {_e}"[:2000]
                db.commit()

        _force_memory_release()  # free Phase 1 temporaries + return pages to OS

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

                import torch as _torch
                _demucs_device = "cuda" if _torch.cuda.is_available() else "cpu"
                logger.info("[bg-analysis] demucs device=%s", _demucs_device)

                result = subprocess.run(
                    [
                        python_exe, "-m", "demucs",
                        "-n", "htdemucs",
                        "-d", _demucs_device,
                        "--segment", "7",   # 7s chunks: good balance of quality vs memory (~2GB peak)
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
                apply_stem_analysis(song)
                song.analysis_stage = "stems_done"
                db.commit()
                logger.info("[bg-analysis] stems separated for %s", song_id)

                # Convert WAV stems to MP3 for faster streaming (WAV ~43MB → MP3 ~4MB)
                import shutil
                ffmpeg = shutil.which("ffmpeg")
                if ffmpeg:
                    for s in stem_names:
                        wav_path = os.path.join(stems_dir, f"{s}.wav")
                        mp3_path = os.path.join(stems_dir, f"{s}.mp3")
                        if os.path.isfile(wav_path) and not os.path.isfile(mp3_path):
                            try:
                                subprocess.run(
                                    [ffmpeg, "-i", wav_path, "-b:a", "192k", "-y", mp3_path],
                                    capture_output=True, timeout=120,
                                )
                            except Exception:
                                logger.warning("[bg-analysis] ffmpeg WAV→MP3 failed for %s/%s", song_id, s)
                    logger.info("[bg-analysis] MP3 stems generated for %s", song_id)
                else:
                    logger.warning("[bg-analysis] ffmpeg not found, skipping MP3 stem conversion")
            else:
                logger.warning("[bg-analysis] stem files not found after demucs for %s", song_id)
        except Exception as _e:
            logger.exception("[bg-analysis] stem separation failed for %s (non-fatal)", song_id)
            # Non-fatal: record error but continue to embedding phase
            try:
                song.analysis_error = f"stems: {_e}"[:2000]
                db.commit()
            except Exception:
                pass

        _force_memory_release()  # free Phase 2 temporaries + return pages to OS

        # --- Phase 3: CLAP audio embedding + ChromaDB indexing ---
        try:
            from app.modules.playlists.models import Song, SongTag
            catalog_song = db.query(Song).filter(Song.id == song.song_id).first() if song.song_id else None
            if catalog_song and song.source_path and os.path.isfile(song.source_path):
                tags = db.query(SongTag).filter(SongTag.song_id == catalog_song.id).first()
                _refresh_analysis_lock()  # reset TTL before CLAP run

                # CLAP audio embedding (subprocess, ~30-60s)
                from app.modules.recommendations.vector_store import index_song_clap, index_song
                ok = index_song_clap(
                    song_id=str(catalog_song.id),
                    audio_path=song.source_path,
                    title=catalog_song.title,
                    artist=catalog_song.artist,
                    style=tags.style if tags else None,
                    energy=tags.energy if tags else None,
                    groove=tags.groove_tag if tags else None,
                    bpm=float(tags.bpm) if tags and tags.bpm else (song.bpm if song.bpm else None),
                )
                if ok:
                    logger.info("[bg-analysis] Phase 3: CLAP audio embedding done for %s", song_id)
                else:
                    logger.warning("[bg-analysis] Phase 3: CLAP embedding failed, using text fallback for %s", song_id)

                # Always index text fallback too
                index_song(
                    song_id=str(catalog_song.id),
                    title=catalog_song.title,
                    artist=catalog_song.artist,
                    style=tags.style if tags else None,
                    energy=tags.energy if tags else None,
                    groove=tags.groove_tag if tags else None,
                    bpm=float(tags.bpm) if tags and tags.bpm else (song.bpm if song.bpm else None),
                )
                song.analysis_stage = "embed_done"
                db.commit()
        except Exception as _e:
            logger.exception("[bg-analysis] Phase 3 indexing failed for %s (non-fatal)", song_id)
            try:
                song.analysis_error = (song.analysis_error or "") + f" | embed: {_e}"
                song.analysis_error = song.analysis_error[:2000]
                db.commit()
            except Exception:
                pass

        # --- Phase 4: DJ-style fingerprint features (cheap, no GPU) ---
        try:
            apply_dj_fingerprint(db, song)
            logger.info("[bg-analysis] Phase 4: dj fingerprint computed for %s", song_id)
        except Exception as _e:
            logger.exception("[bg-analysis] Phase 4 dj fingerprint failed for %s (non-fatal)", song_id)
            try:
                song.analysis_error = (song.analysis_error or "") + f" | dj: {_e}"
                song.analysis_error = song.analysis_error[:2000]
                db.commit()
            except Exception:
                pass

        # Mark completed regardless of stem separation outcome
        from datetime import datetime as _dt
        song.analysis_status = "completed"
        song.analyzed_at = _dt.utcnow()
        db.commit()
    except Exception:
        logger.exception("[bg-analysis] unexpected error for %s", song_id)
    finally:
        db.close()


def copy_analysis_from(source: object, target: object) -> None:
    """Copy analysis results from an existing LibrarySong to a new one."""
    for field in ("bpm", "duration", "key", "camelot_key", "energy",
                  "beat_points", "bpm_curve", "tempo_stability", "energy_curve", "loudness_profile",
                  "transition_windows", "downbeats", "phrase_map", "key_confidence",
                  "stem_activity", "stem_activity_windows", "stem_quality_score",
                  "intro_is_clean", "outro_is_clean", "has_drum_loop",
                  "music_features", "dance_styles", "dance_style_scores", "dance_style_status",
                  "cue_points", "stems", "analysis_status"):
        val = getattr(source, field, None)
        if val is not None:
            setattr(target, field, val)
