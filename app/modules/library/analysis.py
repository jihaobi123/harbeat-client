from __future__ import annotations

import os
import json
import re
import subprocess
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np

from app.modules.library.section_contract import (
    LABEL_CONTRACT_VERSION,
    SECTION_CONTRACT_FIELDS,
    enrich_section_segment,
)
from app.shared.command_line import split_command_line

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ESSENTIA_ANALYSIS_SAMPLE_RATE = 44100
BPM_CONSENSUS_TOLERANCE = 2.0
DOWNBEAT_MATCH_TOLERANCE_SECONDS = 0.07
DOWNBEAT_AGREEMENT_F1 = 0.70
DOWNBEAT_PERIOD_TOLERANCE = 0.12
DOWNBEAT_MAX_INTRO_BARS = 2.0
CORE_ANALYSIS_VERSION = LABEL_CONTRACT_VERSION

_BEAT_THIS_INFERENCE_LOCK = threading.Lock()
_ALL_IN_ONE_INFERENCE_LOCK = threading.Lock()
_SONGFORMER_INFERENCE_LOCK = threading.Lock()
_MADMOM_INFERENCE_LOCK = threading.Lock()
_MADMOM_KEY_INFERENCE_LOCK = threading.Lock()


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def _preload_all_in_one_ffmpeg_libraries() -> str | None:
    """Make local macOS FFmpeg shared libraries visible to TorchCodec.

    macOS does not honor a DYLD path added after the Python process starts.
    Loading the FFmpeg libraries globally before TorchCodec is imported keeps
    direct original-file inference working when HarBeat is launched normally.
    Other platforms use their standard loader configuration unchanged.
    """
    if sys.platform != "darwin":
        return None
    configured = os.getenv("ALL_IN_ONE_FFMPEG_SHARED_LIB_DIR", "").strip()
    lib_dir = (
        Path(configured).expanduser().resolve()
        if configured
        else Path(__file__).resolve().parents[3] / ".runtime" / "ffmpeg-shared" / "lib"
    )
    required = [
        "libavutil.59.dylib",
        "libswresample.5.dylib",
        "libswscale.8.dylib",
        "libavcodec.61.dylib",
        "libavformat.61.dylib",
        "libavfilter.10.dylib",
        "libavdevice.61.dylib",
    ]
    if not all((lib_dir / name).is_file() for name in required):
        return None

    import ctypes

    for name in required:
        ctypes.CDLL(str(lib_dir / name), mode=ctypes.RTLD_GLOBAL)
    return str(lib_dir)


def _bpm_consensus_tolerance() -> float:
    try:
        return float(np.clip(float(os.getenv("BPM_CONSENSUS_TOLERANCE", "2.0")), 0.1, 10.0))
    except (TypeError, ValueError):
        return BPM_CONSENSUS_TOLERANCE


def _downbeat_match_tolerance() -> float:
    try:
        milliseconds = float(os.getenv("DOWNBEAT_MATCH_TOLERANCE_MS", "70"))
        return float(np.clip(milliseconds / 1000.0, 0.02, 0.25))
    except (TypeError, ValueError):
        return DOWNBEAT_MATCH_TOLERANCE_SECONDS


def _downbeat_agreement_f1() -> float:
    try:
        return float(np.clip(float(os.getenv("DOWNBEAT_AGREEMENT_F1", "0.70")), 0.1, 1.0))
    except (TypeError, ValueError):
        return DOWNBEAT_AGREEMENT_F1


def _downbeat_period_tolerance() -> float:
    try:
        return float(np.clip(float(os.getenv("DOWNBEAT_PERIOD_TOLERANCE", "0.12")), 0.03, 0.35))
    except (TypeError, ValueError):
        return DOWNBEAT_PERIOD_TOLERANCE


def _downbeat_max_intro_bars() -> float:
    try:
        return float(np.clip(float(os.getenv("DOWNBEAT_MAX_INTRO_BARS", "2.0")), 0.5, 8.0))
    except (TypeError, ValueError):
        return DOWNBEAT_MAX_INTRO_BARS


def _madmom_beats_per_bar() -> tuple[int, ...]:
    raw = os.getenv("DOWNBEAT_MADMOM_BEATS_PER_BAR", "3,4")
    values: list[int] = []
    for item in raw.split(","):
        try:
            value = int(item.strip())
        except (TypeError, ValueError):
            continue
        if 2 <= value <= 8 and value not in values:
            values.append(value)
    return tuple(values or [3, 4])


def _songformer_timeout_seconds() -> float:
    try:
        return float(np.clip(
            float(os.getenv("SECTION_SONGFORMER_TIMEOUT_SEC", "1800")),
            30.0,
            7200.0,
        ))
    except (TypeError, ValueError):
        return 1800.0


def _songformer_work_dir() -> Path:
    configured = os.getenv("SECTION_SONGFORMER_WORK_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / ".runtime" / "songformer-analysis"


def _songformer_command(audio_path: Path, output_dir: Path) -> list[str]:
    """Build the isolated SongFormer command without invoking a shell.

    A deployment may provide ``SECTION_SONGFORMER_COMMAND`` with ``{audio}``
    and ``{output_dir}`` placeholders.  A developer checkout automatically
    uses the already-installed isolated SongFormer runtime when it is present.
    """
    configured = split_command_line(os.getenv("SECTION_SONGFORMER_COMMAND", ""))
    replacements = {
        "{audio}": str(audio_path),
        "{output_dir}": str(output_dir),
    }
    if configured:
        command = []
        for part in configured:
            for placeholder, value in replacements.items():
                part = part.replace(placeholder, value)
            command.append(part)
        if not any(str(audio_path) == part for part in command):
            command.append(str(audio_path))
        if not any(str(output_dir) == part for part in command):
            command.extend(["--out-dir", str(output_dir)])
        return command

    repository_root = Path(__file__).resolve().parents[3]
    runner = repository_root / "experiments" / "run_songformer_isolated.py"
    python_candidates = [
        repository_root / ".runtime" / "songformer-venv" / "bin" / "python",
        repository_root / ".runtime" / "songformer-venv" / "Scripts" / "python.exe",
    ]
    python_executable = next((path for path in python_candidates if path.is_file()), None)
    if python_executable is None or not runner.is_file():
        raise RuntimeError(
            "SongFormer runtime is unavailable; configure SECTION_SONGFORMER_COMMAND"
        )
    command = [
        str(python_executable),
        str(runner),
        str(audio_path),
        "--out-dir",
        str(output_dir),
        "--device",
        os.getenv("SECTION_SONGFORMER_DEVICE", "auto").strip() or "auto",
        "--precision",
        os.getenv("SECTION_SONGFORMER_PRECISION", "float32").strip() or "float32",
    ]
    source_root = os.getenv("SECTION_SONGFORMER_SOURCE_ROOT", "").strip()
    if source_root:
        command.extend(["--source-root", source_root])
    muq_model = os.getenv("SECTION_SONGFORMER_MUQ_MODEL", "").strip()
    if muq_model:
        command.extend(["--muq-model", muq_model])
    return command


def _normalize_functional_segments(
    segments: list[dict] | None,
    *,
    duration: float | None = None,
    source: str = "songformer_functional_segment",
) -> list[dict]:
    """Validate and normalize one model's functional-section sequence."""
    normalized: list[dict] = []
    upper_bound = float(duration) if duration is not None and duration > 0 else None
    for item in segments or []:
        try:
            start = max(0.0, float(item["start"]))
            end = max(start, float(item["end"]))
            label = str(item["label"]).strip().lower()
        except (KeyError, TypeError, ValueError):
            continue
        if upper_bound is not None:
            start = min(start, upper_bound)
            end = min(end, upper_bound)
        if not label or end <= start:
            continue
        normalized.append(enrich_section_segment({
            **item,
            "start": round(start, 4),
            "end": round(end, 4),
            "label": label,
            **({"label_zh": str(item["label_zh"])} if item.get("label_zh") else {}),
        }, source=source))
    normalized.sort(key=lambda item: (item["start"], item["end"]))
    return normalized


def _select_authoritative_sections(
    songformer_route: dict | None,
    all_in_one_route: dict | None,
    *,
    songformer_error: str | None = None,
) -> tuple[list[dict], dict]:
    """Select one section model without blending boundaries or labels."""
    songformer_segments = _normalize_functional_segments(
        (songformer_route or {}).get("segments"),
        source="songformer_functional_segment",
    )
    all_in_one_segments = _normalize_functional_segments(
        (all_in_one_route or {}).get("segments"),
        source="all_in_one_fallback_functional_segment",
    )
    if songformer_segments:
        return songformer_segments, {
            "source": "songformer_functional_segments",
            "segment_source": "songformer_functional_segment",
            "status": "ok",
            "engine": (songformer_route or {}).get("engine"),
            "route": dict(songformer_route or {}),
            "fallback_used": False,
            "fallback_policy": "all_in_one_only_if_songformer_unavailable",
            "songformer_error": None,
            "all_in_one_segment_count_for_audit": len(all_in_one_segments),
        }

    fallback_enabled = _env_flag("SECTION_FALLBACK_ALL_IN_ONE", True)
    if fallback_enabled and all_in_one_segments:
        return all_in_one_segments, {
            "source": "all_in_one_fallback_functional_segments",
            "segment_source": "all_in_one_fallback_functional_segment",
            "status": "fallback",
            "engine": (all_in_one_route or {}).get("engine"),
            "route": dict(all_in_one_route or {}),
            "fallback_used": True,
            "fallback_policy": "all_in_one_only_if_songformer_unavailable",
            "songformer_error": songformer_error or "SongFormer returned no sections",
            "all_in_one_segment_count_for_audit": len(all_in_one_segments),
        }

    return [], {
        "source": "songformer_unavailable",
        "segment_source": "songformer_functional_segment",
        "status": "unavailable",
        "engine": (songformer_route or {}).get("engine"),
        "route": dict(songformer_route or {}),
        "fallback_used": False,
        "fallback_policy": (
            "all_in_one_only_if_songformer_unavailable"
            if fallback_enabled else "disabled"
        ),
        "songformer_error": songformer_error or "SongFormer returned no sections",
        "all_in_one_segment_count_for_audit": len(all_in_one_segments),
    }


def _songformer_payload_from_output(
    output_dir: Path,
    audio_path: Path,
    stdout: str,
) -> dict:
    """Read either the official-runner manifest or a custom worker JSON."""
    manifest_path = output_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        resolved_audio = str(audio_path.resolve())
        tracks = list(manifest.get("tracks") or [])
        record = next(
            (item for item in reversed(tracks) if item.get("audio_path") == resolved_audio),
            tracks[-1] if len(tracks) == 1 else None,
        )
        if record is None:
            raise ValueError("SongFormer manifest has no matching track")
        if record.get("error"):
            raise RuntimeError(str(record["error"]))
        return {
            **record,
            "model": manifest.get("model"),
            "pipeline": manifest.get("pipeline"),
            "device": manifest.get("device"),
            "frame_rate": manifest.get("frame_rate"),
            "runner_version": manifest.get("runner_version"),
            "label_contract_version": manifest.get("label_contract_version"),
            "runtime_fingerprint": manifest.get("runtime_fingerprint"),
            "cache_namespace": manifest.get("cache_namespace"),
        }

    result_path = output_dir / "songformer_result.json"
    if result_path.is_file():
        return json.loads(result_path.read_text(encoding="utf-8"))

    text = stdout.strip()
    if text:
        try:
            payload = json.loads(text)
            if isinstance(payload, dict) and payload.get("segments"):
                return payload
        except json.JSONDecodeError:
            pass
        for line in reversed(text.splitlines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("segments"):
                return payload
    raise ValueError("SongFormer worker produced no section result")


def _analyze_sections_songformer(file_path: str | os.PathLike[str]) -> dict:
    """Run SongFormer as the authoritative functional-section model."""
    audio_path = Path(file_path).expanduser().resolve()
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)
    output_dir = _songformer_work_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    command = _songformer_command(audio_path, output_dir)
    with _SONGFORMER_INFERENCE_LOCK:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_songformer_timeout_seconds(),
            check=False,
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-2000:]
        raise RuntimeError(
            f"SongFormer worker exited with {completed.returncode}: {detail}"
        )
    payload = _songformer_payload_from_output(output_dir, audio_path, completed.stdout)
    segments = _normalize_functional_segments(
        payload.get("segments"),
        duration=payload.get("duration"),
        source="songformer_functional_segment",
    )
    if not segments:
        raise ValueError("SongFormer returned no functional sections")
    return {
        "segments": segments,
        "engine": "songformer:ASLP-lab/SongFormer",
        "model": payload.get("model") or "ASLP-lab/SongFormer",
        "pipeline": payload.get("pipeline"),
        "device": payload.get("device"),
        "frame_rate": payload.get("frame_rate"),
        "runner_version": payload.get("runner_version"),
        "label_contract_version": payload.get("label_contract_version"),
        "runtime_fingerprint": payload.get("runtime_fingerprint"),
        "cache_namespace": payload.get("cache_namespace"),
        "input_mode": "original_audio_file",
        "input_path": str(audio_path),
        "sample_rate": 24_000,
        "method": "songformer_functional_structure",
    }

MAJOR_TEMPLATE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_TEMPLATE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NOTE_MODE_TO_CAMELOT = {
    ("C", "major"): "8B", ("C#", "major"): "3B", ("D", "major"): "10B",
    ("D#", "major"): "5B", ("E", "major"): "12B", ("F", "major"): "7B",
    ("F#", "major"): "2B", ("G", "major"): "9B", ("G#", "major"): "4B",
    ("A", "major"): "11B", ("A#", "major"): "6B", ("B", "major"): "1B",
    ("C", "minor"): "5A", ("C#", "minor"): "12A", ("D", "minor"): "7A",
    ("D#", "minor"): "2A", ("E", "minor"): "9A", ("F", "minor"): "4A",
    ("F#", "minor"): "11A", ("G", "minor"): "6A", ("G#", "minor"): "1A",
    ("A", "minor"): "8A", ("A#", "minor"): "3A", ("B", "minor"): "10A",
}
CAMELOT_TO_NOTE_MODE = {value: key for key, value in NOTE_MODE_TO_CAMELOT.items()}

FLAT_TO_SHARP = {
    "Db": "C#",
    "Eb": "D#",
    "Gb": "F#",
    "Ab": "G#",
    "Bb": "A#",
}

# Camelot number lookup for distance calculation
CAMELOT_NUMBER = {v: (int(v[:-1]), v[-1]) for v in NOTE_MODE_TO_CAMELOT.values()}

CUE_COLORS = ["#22c55e", "#3b82f6", "#ef4444", "#f59e0b", "#8b5cf6", "#ec4899", "#06b6d4", "#64748b"]

# ── DJ Hot Cue semantic labels ──────────────────────────────────────────────
DJ_HOT_CUE_DEFS = [
    {"name": "intro_end",     "label": "Intro End",    "color": "#22c55e", "desc": "前奏结束，鼓点/贝斯进入"},
    {"name": "main_groove",   "label": "Main Groove",  "color": "#3b82f6", "desc": "主律动段，最适合跳舞"},
    {"name": "first_drop",    "label": "First Drop",   "color": "#ef4444", "desc": "第一个高潮/爆点"},
    {"name": "best_loop",     "label": "Best Loop",    "color": "#f59e0b", "desc": "最适合 Loop 的段落"},
    {"name": "outro_start",   "label": "Outro Start",  "color": "#64748b", "desc": "尾奏开始，适合作为切出点"},
]


def _generate_dj_hot_cues(
    phrase_map: list[dict],
    transition_windows: list[dict],
    energy_curve: list[dict],
    duration: float,
) -> list[dict]:
    """Generate DJ-oriented hot cue points from structural analysis.

    Returns 5 semantic cue points: intro_end, main_groove, first_drop,
    best_loop, outro_start. Each includes time, confidence, and the
    reasoning (which phrase/section was used).
    """
    cues: list[dict] = []
    pm = phrase_map or []
    tw = transition_windows or []

    if not pm:
        return cues

    # ── intro_end: exact authoritative-model intro boundary ──
    intro_end_time = None
    saw_intro = False
    intro_source = "functional_segment"
    for index, p in enumerate(pm):
        label = str(p.get("label", "")).lower()
        if label == "intro" and (index == 0 or saw_intro):
            saw_intro = True
            intro_end_time = float(p.get("end", p.get("start", 0)))
            intro_source = str(p.get("source") or intro_source).replace(
                "_functional_segment", ""
            )
            continue
        if saw_intro:
            break
        break
    if intro_end_time is None and pm:
        intro_end_time = float(pm[0].get("start", 0))
    if intro_end_time is not None:
        cues.append({
            "name": "intro_end", "label": "Intro End",
            "time": round(intro_end_time, 2),
            "color": "#22c55e",
            "confidence": 0.9 if saw_intro else 0.5,
            "source": (
                f"{intro_source}_intro_boundary"
                if saw_intro else f"{intro_source}_first_section_start_no_intro_label"
            ),
        })

    # ── main_groove: highest intensity section ──
    best_groove = max(pm, key=lambda p: float(p.get("intensity", p.get("energy", 0))))
    cues.append({
        "name": "main_groove", "label": "Main Groove",
        "time": round(float(best_groove.get("start", 0)), 2),
        "color": "#3b82f6",
        "confidence": round(float(best_groove.get("intensity", 0.5)), 3),
        "source": f"phrase={best_groove.get('label', '?')}",
    })

    # ── first_drop: first peak section ──
    first_drop = None
    for p in pm:
        if p.get("is_peak_section") or p.get("label") in ("drop",):
            first_drop = p
            break
    if first_drop is None:
        # fallback: highest energy section
        first_drop = max(pm, key=lambda p: float(p.get("energy", 0)))
    cues.append({
        "name": "first_drop", "label": "First Drop",
        "time": round(float(first_drop.get("start", 0)), 2),
        "color": "#ef4444",
        "confidence": round(float(first_drop.get("intensity", first_drop.get("energy", 0.5))), 3),
        "source": f"phrase={first_drop.get('label', '?')}",
    })

    # ── best_loop: highest mix_in_score + clean_candidate ──
    best_loop_window = None
    best_loop_score = -1.0
    for w in tw:
        if w.get("clean_candidate"):
            score = float(w.get("mix_in_score", 0)) * 0.6 + float(w.get("mix_out_score", 0)) * 0.4
            if score > best_loop_score:
                best_loop_score = score
                best_loop_window = w
    if best_loop_window is None and tw:
        best_loop_window = max(tw, key=lambda w: float(w.get("mix_in_score", 0)))
    if best_loop_window:
        cues.append({
            "name": "best_loop", "label": "Best Loop",
            "time": round(float(best_loop_window.get("start", 0)), 2),
            "color": "#f59e0b",
            "confidence": round(float(best_loop_window.get("mix_in_score", 0.5)), 3),
            "source": f"label={best_loop_window.get('label', '?')} tags={best_loop_window.get('stem_tags', [])}",
        })

    # ── outro_start: last phrase with label outro, or last breakdown ──
    outro_start_time = None
    for p in reversed(pm):
        if p.get("label") in ("outro",):
            outro_start_time = float(p.get("start", 0))
            break
    if outro_start_time is None:
        # fallback: last breakdown, or 80% of duration
        for p in reversed(pm):
            if p.get("label") in ("breakdown",) and float(p.get("start", 0)) > duration * 0.6:
                outro_start_time = float(p.get("start", 0))
                break
    if outro_start_time is None:
        outro_start_time = duration * 0.8
    cues.append({
        "name": "outro_start", "label": "Outro Start",
        "time": round(outro_start_time, 2),
        "color": "#64748b",
        "confidence": 0.7,
        "source": "phrase_label" if any(p.get("label") == "outro" for p in pm) else "duration_fallback",
    })

    return cues


# ═══════════════════════════════════════════════════════════════════════════════
# Key / tonal analysis — comprehensive DJ-oriented key detection
# ═══════════════════════════════════════════════════════════════════════════════

def _clamp01(value: Any, default: float = 0.0) -> float:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        raw = default
    return float(np.clip(raw, 0.0, 1.0))


def _normalize_note_name(note: str) -> str:
    raw = str(note or "").strip()
    if not raw:
        return "C"
    raw = raw[0].upper() + raw[1:]
    return FLAT_TO_SHARP.get(raw, raw)


def _normalize_scale_name(scale: str) -> str:
    raw = str(scale or "").strip().lower()
    if raw in {"major", "maj"}:
        return "major"
    if raw in {"minor", "min"}:
        return "minor"
    return raw


def _key_result_from_camelot(
    camelot: str,
    *,
    engine: str,
    method: str,
    confidence: float = 0.0,
    **details: Any,
) -> dict:
    normalized = str(camelot or "").strip().upper()
    note_mode = CAMELOT_TO_NOTE_MODE.get(normalized)
    if note_mode is None:
        raise ValueError(f"unsupported Camelot key: {camelot!r}")
    root, mode = note_mode
    score = _clamp01(confidence)
    return {
        "key": f"{root} {mode}",
        "camelot_key": normalized,
        "key_confidence": round(score, 4),
        "tonal_clarity": round(score, 4),
        "relative_ambiguity": False,
        "candidates": [{
            "root": root,
            "mode": mode,
            "camelot": normalized,
            "score": round(score, 4),
            "source": method,
        }],
        "method": method,
        "engine": engine,
        **details,
    }


def _parse_keyfinder_camelot(output: str) -> str:
    """Extract a Camelot key from keyfinder-cli stdout."""
    matches = re.findall(r"(?<![0-9A-Z])(1[0-2]|[1-9])([AB])(?![0-9A-Z])", str(output).upper())
    if not matches:
        raise ValueError(f"keyfinder-cli returned no Camelot key: {output!r}")
    return f"{matches[-1][0]}{matches[-1][1]}"


def _run_keyfinder_cli(file_path: str) -> str:
    command = split_command_line(os.getenv("KEYFINDER_CLI", "keyfinder-cli"))
    if not command:
        raise RuntimeError("KEYFINDER_CLI is empty")
    try:
        timeout = float(os.getenv("KEYFINDER_TIMEOUT_SECONDS", "180"))
    except ValueError:
        timeout = 180.0
    completed = subprocess.run(
        [*command, "-n", "camelot", str(file_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=max(10.0, timeout),
    )
    return _parse_keyfinder_camelot(completed.stdout)


def _analyze_key_libkeyfinder(file_path: str, y: np.ndarray, sr: int) -> dict:
    """Primary DJ key route using libKeyFinder through keyfinder-cli.

    The whole track is always analyzed. For tracks of at least one minute, a
    body crop and a centre crop are also analyzed to expose intros, outros and
    local modulations instead of hiding them behind one global label.
    """
    route_results: list[dict[str, str]] = [{
        "segment": "full",
        "camelot": _run_keyfinder_cli(file_path),
    }]

    audio = np.asarray(y, dtype=np.float32)
    duration = len(audio) / max(1, int(sr))
    if _env_flag("KEYFINDER_ENABLE_SEGMENTS") and duration >= 60.0:
        import soundfile as sf

        segment_specs = [
            ("body", int(len(audio) * 0.10), int(len(audio) * 0.90)),
            ("center", max(0, len(audio) // 2 - int(sr * 45)), min(len(audio), len(audio) // 2 + int(sr * 45))),
        ]
        with TemporaryDirectory(prefix="harbeat-keyfinder-") as temp_dir:
            for label, start, end in segment_specs:
                segment_path = str(Path(temp_dir) / f"{label}.wav")
                sf.write(segment_path, audio[start:end], int(sr), subtype="PCM_16")
                try:
                    route_results.append({
                        "segment": label,
                        "camelot": _run_keyfinder_cli(segment_path),
                    })
                except Exception as exc:
                    route_results.append({
                        "segment": label,
                        "error": f"{type(exc).__name__}: {exc}",
                    })

    successful = [item["camelot"] for item in route_results if item.get("camelot")]
    counts = Counter(successful)
    # Counter preserves insertion order, so a tie intentionally favours the
    # full-track result, which is the first and canonical libKeyFinder pass.
    selected, votes = counts.most_common(1)[0]
    stability = votes / len(successful)
    return _key_result_from_camelot(
        selected,
        engine="libkeyfinder",
        method="libkeyfinder_global_segment_consensus",
        confidence=stability,
        route_stability=round(stability, 4),
        segment_results=route_results,
        command=command[0] if (command := split_command_line(os.getenv("KEYFINDER_CLI", "keyfinder-cli"))) else "keyfinder-cli",
    )


def _analyze_key_madmom(file_path: str) -> dict:
    """Independent 24-class CNN verification route from madmom."""
    external_command = split_command_line(os.getenv("KEY_MADMOM_COMMAND", ""))
    if not external_command:
        adapter = Path(__file__).parents[3] / "scripts" / "madmom_key_cli.py"
        if adapter.is_file():
            external_command = [sys.executable, str(adapter)]
    if external_command:
        completed = subprocess.run(
            [*external_command, str(file_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=max(10.0, float(os.getenv("KEY_MADMOM_TIMEOUT_SECONDS", "180"))),
        )
        payload = json.loads(completed.stdout)
        label = str(payload["key"])
        root_raw, mode_raw = label.rsplit(" ", 1)
        root = _normalize_note_name(root_raw)
        mode = _normalize_scale_name(mode_raw)
        camelot = NOTE_MODE_TO_CAMELOT.get((root, mode))
        if camelot is None:
            raise ValueError(f"unsupported madmom key result: {label}")
        return _key_result_from_camelot(
            camelot,
            engine="madmom_cnn",
            method="madmom_cnn_key_recognition_external",
            confidence=_clamp01(payload.get("confidence")),
            raw_label=label,
            candidates=payload.get("candidates", []),
            model_version=payload.get("model_version"),
            worker_engine=payload.get("engine"),
        )

    with _MADMOM_KEY_INFERENCE_LOCK:
        from madmom.features.key import (  # type: ignore[import-not-found]
            CNNKeyRecognitionProcessor,
            KEY_LABELS,
        )
        probabilities = np.asarray(CNNKeyRecognitionProcessor()(file_path), dtype=float).reshape(-1)
    if probabilities.size != len(KEY_LABELS):
        raise ValueError(f"madmom returned {probabilities.size} classes, expected {len(KEY_LABELS)}")
    class_index = int(np.argmax(probabilities))
    label = str(KEY_LABELS[class_index])
    root_raw, mode_raw = label.rsplit(" ", 1)
    root = _normalize_note_name(root_raw)
    mode = _normalize_scale_name(mode_raw)
    camelot = NOTE_MODE_TO_CAMELOT.get((root, mode))
    if camelot is None:
        raise ValueError(f"unsupported madmom key result: {label}")
    confidence = _clamp01(probabilities[class_index])
    top_indices = np.argsort(probabilities)[::-1][:3]
    candidates = []
    for index in top_indices:
        candidate_root_raw, candidate_mode_raw = str(KEY_LABELS[int(index)]).rsplit(" ", 1)
        candidate_root = _normalize_note_name(candidate_root_raw)
        candidate_mode = _normalize_scale_name(candidate_mode_raw)
        candidates.append({
            "root": candidate_root,
            "mode": candidate_mode,
            "camelot": NOTE_MODE_TO_CAMELOT[(candidate_root, candidate_mode)],
            "score": round(_clamp01(probabilities[int(index)]), 4),
            "source": "madmom_cnn",
        })
    result = _key_result_from_camelot(
        camelot,
        engine="madmom_cnn",
        method="madmom_cnn_key_recognition",
        confidence=confidence,
        raw_label=label,
    )
    result["candidates"] = candidates
    return result


def _choose_key_consensus(
    route_results: dict[str, dict],
    *,
    errors: dict[str, str] | None = None,
    local_fallback: dict | None = None,
) -> dict:
    """Confirm a held-out-validated key route or return a reviewable candidate."""
    errors = dict(errors or {})
    primary = route_results.get("libkeyfinder")
    validators = [
        route_results[name]
        for name in ("essentia", "madmom")
        if name in route_results
    ]
    from app.modules.library.key_model_validation import resolve_key_model_validation

    key_model_validation = resolve_key_model_validation(route_results.get("madmom"))
    validated_route = (
        route_results.get("madmom") if key_model_validation.get("validated") else None
    )

    selected: dict
    decision: str
    confidence_level: str
    decision_confidence: float

    if validated_route is not None:
        selected = validated_route
        decision = "heldout_validated_madmom"
        confidence_level = "validated"
        decision_confidence = float(key_model_validation["heldout_exact_accuracy"])
    elif primary is not None:
        primary_key = primary["camelot_key"]
        agreeing = [item for item in validators if item["camelot_key"] == primary_key]
        if agreeing:
            selected, decision, confidence_level, decision_confidence = primary, "primary_confirmed", "high", 0.95
        elif len(validators) == 2 and validators[0]["camelot_key"] == validators[1]["camelot_key"]:
            selected, decision, confidence_level, decision_confidence = validators[0], "validators_override_primary", "high", 0.9
        elif len(validators) == 2:
            fallback_key = (local_fallback or {}).get("camelot_key")
            fallback_match = next(
                (item for item in [primary, *validators] if item["camelot_key"] == fallback_key),
                None,
            )
            if fallback_match is not None:
                selected, decision, confidence_level, decision_confidence = fallback_match, "local_tiebreak", "low", 0.55
            else:
                selected, decision, confidence_level, decision_confidence = primary, "primary_unresolved_conflict", "low", 0.4
        else:
            selected, decision, confidence_level, decision_confidence = primary, "primary_unconfirmed", "medium", 0.65
    elif validators:
        if len(validators) == 2 and validators[0]["camelot_key"] == validators[1]["camelot_key"]:
            selected, decision, confidence_level, decision_confidence = validators[0], "validators_agree_primary_unavailable", "high", 0.85
        else:
            fallback_key = (local_fallback or {}).get("camelot_key")
            selected = next((item for item in validators if item["camelot_key"] == fallback_key), validators[0])
            decision = "validator_fallback"
            confidence_level = "medium" if selected["camelot_key"] == fallback_key else "low"
            decision_confidence = 0.65 if confidence_level == "medium" else 0.45
    elif local_fallback is not None:
        selected, decision, confidence_level, decision_confidence = local_fallback, "local_only_fallback", "low", 0.35
    else:
        raise RuntimeError("all key detection routes failed")

    if validated_route is None:
        # Route agreement is useful diagnostic evidence, but GiantSteps shows
        # it is not a calibrated probability. Never emit the old fabricated
        # 0.90/0.95 confidence for an unvalidated candidate.
        decision_confidence = min(
            float(selected.get("key_confidence") or decision_confidence or 0.0), 0.79,
        )
        confidence_level = "provisional"

    public = dict(selected)
    public["model_confidence"] = round(float(selected.get("key_confidence") or 0.0), 4)
    public["key_confidence"] = round(decision_confidence, 4)
    public["decision"] = decision
    public["confidence_level"] = confidence_level
    public["primary_engine"] = "libkeyfinder"
    public["selected_engine"] = selected.get("engine")
    public["needs_review"] = validated_route is None
    public["validation_status"] = "validated" if validated_route is not None else "provisional"
    public["model_validation"] = key_model_validation
    public["route_results"] = {
        name: {
            "key": result.get("key"),
            "camelot_key": result.get("camelot_key"),
            "confidence": result.get("key_confidence"),
            "engine": result.get("engine"),
            "route_stability": result.get("route_stability"),
            "segment_results": result.get("segment_results"),
            "model_version": result.get("model_version"),
            "worker_engine": result.get("worker_engine"),
        }
        for name, result in route_results.items()
    }
    if local_fallback is not None:
        public["local_fallback"] = {
            "key": local_fallback.get("key"),
            "camelot_key": local_fallback.get("camelot_key"),
            "confidence": local_fallback.get("key_confidence"),
        }
    public["errors"] = errors
    return public


def _prepare_essentia_audio(y: np.ndarray, sr: int, *, max_duration: float | None = None) -> np.ndarray:
    """Return mono float32 audio at the sample rate expected by Essentia.

    Essentia's old source build can be compiled without FFmpeg loaders on
    Jetson, so HarBeat decodes the file once with the existing Python audio
    stack and passes the decoded signal into Essentia's BPM/key algorithms.
    """
    import librosa

    audio = np.asarray(y, dtype=np.float32)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=0).astype(np.float32)
    if int(sr) != ESSENTIA_ANALYSIS_SAMPLE_RATE:
        audio = librosa.resample(
            audio,
            orig_sr=int(sr),
            target_sr=ESSENTIA_ANALYSIS_SAMPLE_RATE,
        ).astype(np.float32)
    if max_duration is not None and max_duration > 0:
        audio = audio[: int(max_duration * ESSENTIA_ANALYSIS_SAMPLE_RATE)]
    if len(audio) < ESSENTIA_ANALYSIS_SAMPLE_RATE:
        raise ValueError("audio too short for Essentia analysis")
    return np.ascontiguousarray(audio, dtype=np.float32)


def _analyze_key_essentia(y: np.ndarray, sr: int, *, max_duration: float | None = None) -> dict:
    """Detect musical key with Essentia KeyExtractor.

    This is the preferred DJ-facing key path. HarBeat decodes audio with its
    existing Python stack, then Essentia analyzes the decoded 44.1 kHz signal.
    """
    import essentia.standard as es

    audio = _prepare_essentia_audio(y, sr, max_duration=max_duration)
    raw_key, raw_scale, strength = es.KeyExtractor()(audio)
    root = _normalize_note_name(raw_key)
    mode = _normalize_scale_name(raw_scale)
    camelot = NOTE_MODE_TO_CAMELOT.get((root, mode))
    if camelot is None:
        raise ValueError(f"unsupported Essentia key result: {raw_key} {raw_scale}")

    confidence = _clamp01(strength)
    return {
        "key": f"{root} {mode}",
        "camelot_key": camelot,
        "key_confidence": round(confidence, 4),
        "tonal_clarity": round(confidence, 4),
        "relative_ambiguity": False,
        "candidates": [{
            "root": root,
            "mode": mode,
            "camelot": camelot,
            "score": round(confidence, 4),
            "source": "essentia_keyextractor",
        }],
        "method": "essentia_keyextractor",
        "engine": "essentia",
        "sample_rate": ESSENTIA_ANALYSIS_SAMPLE_RATE,
        "raw_key": str(raw_key),
        "raw_scale": str(raw_scale),
        "strength": round(confidence, 4),
    }


def _analyze_rhythm_essentia(y: np.ndarray, sr: int, *, max_duration: float | None = None) -> dict:
    """Detect BPM and beat ticks with Essentia RhythmExtractor2013."""
    import essentia.standard as es

    audio = _prepare_essentia_audio(y, sr, max_duration=max_duration)
    bpm, beats, confidence, estimates, bpm_intervals = es.RhythmExtractor2013(method="multifeature")(audio)
    beat_times = np.asarray(beats, dtype=float)
    if len(beat_times) == 0:
        raise ValueError("Essentia RhythmExtractor2013 returned no beat ticks")

    candidates = []
    try:
        for estimate in list(estimates)[:8]:
            candidates.append({"bpm": round(float(estimate), 3), "source": "essentia_estimate"})
    except Exception:
        candidates = []
    if not candidates:
        candidates = [{"bpm": round(float(bpm), 3), "source": "essentia_bpm"}]

    return {
        "bpm": float(bpm),
        "beat_times": beat_times,
        "confidence": _clamp01(confidence),
        "bpm_candidates": candidates,
        "bpm_intervals": [round(float(x), 6) for x in list(bpm_intervals)[:16]],
        "engine": "essentia_rhythmextractor2013",
        "sample_rate": ESSENTIA_ANALYSIS_SAMPLE_RATE,
        "method": "multifeature",
    }


def _bpm_from_beat_times(beat_times: list[float] | np.ndarray) -> float:
    """Estimate a stable global BPM from an engine's detected beat positions."""
    beats = np.asarray(beat_times, dtype=float)
    intervals = np.diff(beats)
    intervals = intervals[(intervals >= 0.18) & (intervals <= 2.0)]
    if len(intervals) < 2:
        raise ValueError("not enough valid beat intervals to estimate BPM")
    return float(60.0 / np.median(intervals))


def _resolve_torch_device(env_name: str, *, prefer_accelerator: bool) -> str:
    """Resolve an optional device override without importing torch at module load."""
    override = os.getenv(env_name, "").strip().lower()
    if override:
        return override
    if not prefer_accelerator:
        return "cpu"
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


@lru_cache(maxsize=4)
def _load_beat_this_analyzer(model_name: str, device: str):
    from beat_this.inference import Audio2Frames
    from beat_this.model.postprocessor import Postprocessor

    return (
        Audio2Frames(checkpoint_path=model_name, device=device, float16=False),
        Postprocessor(type="minimal", fps=50),
    )


def _analyze_rhythm_beat_this(y: np.ndarray, sr: int) -> dict:
    """Run the Beat This model and derive BPM from its predicted beat grid."""
    model_name = os.getenv("BPM_BEAT_THIS_MODEL", "final0").strip() or "final0"
    device = _resolve_torch_device("BPM_BEAT_THIS_DEVICE", prefer_accelerator=False)
    analyzer, postprocessor = _load_beat_this_analyzer(model_name, device)
    with _BEAT_THIS_INFERENCE_LOCK:
        beat_logits, downbeat_logits = analyzer(np.asarray(y, dtype=np.float32), int(sr))
        beats, downbeats = postprocessor(beat_logits, downbeat_logits)
    beat_times = np.asarray(beats, dtype=float)
    if len(beat_times) == 0:
        raise ValueError("Beat This returned no beat ticks")
    bpm = _bpm_from_beat_times(beat_times)
    intervals = np.diff(beat_times)
    interval_mean = float(np.mean(intervals)) if len(intervals) else 0.0
    confidence = (
        float(np.clip(1.0 - np.std(intervals) / interval_mean, 0.0, 1.0))
        if interval_mean > 0 else 0.0
    )
    import torch

    downbeat_array = np.asarray(downbeats, dtype=float)
    downbeat_frames = np.clip(
        np.rint(downbeat_array * 50.0).astype(int), 0, max(0, len(downbeat_logits) - 1),
    )
    downbeat_peak_probability = (
        float(torch.sigmoid(downbeat_logits[downbeat_frames]).mean().item())
        if len(downbeat_frames) and len(downbeat_logits) else 0.0
    )
    route = {
        "bpm": bpm,
        "beat_times": beat_times,
        "downbeats": [round(float(x), 3) for x in downbeat_array],
        "confidence": confidence,
        "downbeat_peak_probability_mean": round(downbeat_peak_probability, 4),
        "bpm_candidates": [{"bpm": round(bpm, 3), "source": "beat_this_grid"}],
        "bpm_intervals": [round(float(x), 6) for x in list(intervals)[:16]],
        "engine": f"beat_this:{model_name}",
        "sample_rate": int(sr),
        "method": "median_detected_beat_interval",
        "postprocessor": "minimal_50fps_probability_gt_0.5_peak_nms_70ms",
    }
    from app.modules.library.beat_model_validation import resolve_beat_model_validation

    route["model_validation"] = resolve_beat_model_validation(route)
    return route


def _analyze_rhythm_all_in_one(
    y: np.ndarray,
    sr: int,
    *,
    file_path: str | os.PathLike[str] | None = None,
) -> dict:
    """Run the native All-In-One pipeline.

    Production analysis passes ``file_path`` so All-In-One receives the
    original audio file directly.  The decoded-array compatibility path is
    retained only for isolated callers that do not have a source path.
    """
    ffmpeg_shared_lib_dir = _preload_all_in_one_ffmpeg_libraries()

    import soundfile as sf
    from allin1_infer import analyze

    model_name = os.getenv("BPM_ALL_IN_ONE_MODEL", "harmonix-all").strip() or "harmonix-all"
    device = _resolve_torch_device("BPM_ALL_IN_ONE_DEVICE", prefer_accelerator=True)
    with TemporaryDirectory(prefix="harbeat-all-in-one-") as tmp:
        tmp_path = Path(tmp)
        if file_path is not None:
            analysis_path = Path(file_path).expanduser().resolve()
            if not analysis_path.is_file():
                raise FileNotFoundError(analysis_path)
            input_mode = "original_audio_file"
            try:
                source_sample_rate = int(sf.info(str(analysis_path)).samplerate)
            except Exception:
                source_sample_rate = None
        else:
            analysis_path = tmp_path / "analysis.wav"
            sf.write(
                analysis_path,
                np.asarray(y, dtype=np.float32),
                int(sr),
                subtype="FLOAT",
            )
            input_mode = "decoded_float_wav_compatibility"
            source_sample_rate = int(sr)
        with _ALL_IN_ONE_INFERENCE_LOCK:
            result = analyze(
                analysis_path,
                model=model_name,
                device=device,
                multiprocess=False,
                demix_dir=tmp_path / "demix",
                spec_dir=tmp_path / "spec",
                keep_byproducts=False,
            )

    beat_times = np.asarray(result.beats, dtype=float)
    if len(beat_times) == 0:
        raise ValueError("All-In-One returned no beat ticks")
    bpm = float(result.bpm) if result.bpm else _bpm_from_beat_times(beat_times)
    intervals = np.diff(beat_times)
    interval_mean = float(np.mean(intervals)) if len(intervals) else 0.0
    confidence = (
        float(np.clip(1.0 - np.std(intervals) / interval_mean, 0.0, 1.0))
        if interval_mean > 0 else 0.0
    )
    segments = []
    raw_segments = getattr(result, "segments", None)
    for segment in list(raw_segments) if raw_segments is not None else []:
        try:
            if isinstance(segment, dict):
                start, end, label = segment["start"], segment["end"], segment["label"]
            else:
                start, end, label = segment.start, segment.end, segment.label
            segments.append({
                "start": round(float(start), 4),
                "end": round(float(end), 4),
                "label": str(label).lower(),
            })
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return {
        "bpm": bpm,
        "beat_times": beat_times,
        "downbeats": [round(float(x), 3) for x in np.asarray(result.downbeats, dtype=float)],
        "beat_positions": [
            int(value) for value in (
                list(getattr(result, "beat_positions"))
                if getattr(result, "beat_positions", None) is not None else []
            )
        ],
        "segments": segments,
        "confidence": confidence,
        "bpm_candidates": [{"bpm": round(bpm, 3), "source": "all_in_one"}],
        "bpm_intervals": [round(float(x), 6) for x in list(intervals)[:16]],
        "engine": f"all_in_one:{model_name}",
        "sample_rate": source_sample_rate,
        "input_mode": input_mode,
        "input_path": str(analysis_path) if input_mode == "original_audio_file" else None,
        "ffmpeg_shared_lib_dir": ffmpeg_shared_lib_dir,
        "method": "all_in_one_model",
    }


@lru_cache(maxsize=4)
def _load_madmom_downbeat_processors(beats_per_bar: tuple[int, ...]):
    from madmom_infer.features.downbeats import (
        DBNDownBeatTrackingProcessor,
        RNNDownBeatProcessor,
    )

    activation_processor = RNNDownBeatProcessor()
    tracking_processor = DBNDownBeatTrackingProcessor(
        beats_per_bar=list(beats_per_bar),
        fps=100,
    )
    return activation_processor, tracking_processor


def _analyze_downbeats_madmom(y: np.ndarray, sr: int) -> dict:
    """Run the independent madmom BLSTM+DBN downbeat tracking route."""
    audio = _prepare_essentia_audio(y, sr, max_duration=MAX_ANALYSIS_DURATION)
    beats_per_bar = _madmom_beats_per_bar()
    activation_processor, tracking_processor = _load_madmom_downbeat_processors(beats_per_bar)
    with _MADMOM_INFERENCE_LOCK:
        # The BLSTM front end creates three full-resolution spectrogram views.
        # Processing long songs in one call can exceed container RAM, so build
        # activations in overlapping chunks and run the continuity-enforcing
        # DBN once over the stitched full-song activation sequence.
        sample_rate = ESSENTIA_ANALYSIS_SAMPLE_RATE
        chunk_samples = 60 * sample_rate
        overlap_samples = 5 * sample_rate
        activation_chunks: list[np.ndarray] = []
        for core_start in range(0, len(audio), chunk_samples):
            core_end = min(core_start + chunk_samples, len(audio))
            expanded_start = max(0, core_start - overlap_samples)
            expanded_end = min(len(audio), core_end + overlap_samples)
            expanded = np.asarray(
                activation_processor(audio[expanded_start:expanded_end]),
                dtype=float,
            )
            keep_start = int(round((core_start - expanded_start) / sample_rate * 100))
            expected_frames = int(round((core_end - core_start) / sample_rate * 100))
            activation_chunks.append(expanded[keep_start:keep_start + expected_frames])
        activations = np.concatenate(activation_chunks, axis=0) if activation_chunks else np.empty((0, 2))
        tracked = np.asarray(tracking_processor(activations), dtype=float)
    if tracked.ndim != 2 or tracked.shape[1] < 2 or len(tracked) == 0:
        raise ValueError("madmom returned no beat/downbeat ticks")

    downbeat_mask = np.rint(tracked[:, 1]).astype(int) == 1
    downbeats = tracked[downbeat_mask, 0]
    if len(downbeats) == 0:
        raise ValueError("madmom returned no downbeats")
    frames = np.clip(np.rint(downbeats * 100).astype(int), 0, max(len(activations) - 1, 0))
    confidence = float(np.mean(activations[frames, 1])) if len(activations) else 0.0
    return {
        "beat_times": np.asarray(tracked[:, 0], dtype=float),
        "downbeats": [round(float(value), 3) for value in downbeats],
        "beat_positions": [int(round(value)) for value in tracked[:, 1]],
        "confidence": float(np.clip(confidence, 0.0, 1.0)),
        "engine": "madmom_infer:rnn_dbn",
        "method": "blstm_dbn_downbeat_tracking",
        "beats_per_bar": list(beats_per_bar),
        "sample_rate": ESSENTIA_ANALYSIS_SAMPLE_RATE,
    }


def _choose_bpm_consensus(
    results: dict[str, dict],
    *,
    tolerance: float = BPM_CONSENSUS_TOLERANCE,
    preferred_engine: str = "beat_this",
) -> dict:
    """Resolve BPM value and metrical level as two different decisions.

    Values within ``tolerance`` of the calibrated metrical-reference engine are
    averaged robustly.  Half/double-tempo aliases are *not* ordinary majority
    votes: two engines can agree with each other at the wrong metrical level.
    GiantSteps calibration/heldout evaluation selects Beat This as the level
    reference.  If it is unavailable, the largest exact-value group remains the
    deterministic degraded fallback.
    """
    valid = {
        name: value for name, value in results.items()
        if np.isfinite(float(value.get("bpm", 0.0))) and float(value.get("bpm", 0.0)) > 0
    }
    if not valid:
        raise ValueError("all BPM engines failed")

    canonical_order = ["beat_this", "all_in_one", "essentia"]
    names = [name for name in canonical_order if name in valid]
    names.extend(sorted(name for name in valid if name not in canonical_order))
    groups: list[list[str]] = []
    for mask in range(1, 1 << len(names)):
        group = [names[index] for index in range(len(names)) if mask & (1 << index)]
        bpms = [float(valid[name]["bpm"]) for name in group]
        if max(bpms) - min(bpms) <= tolerance:
            groups.append(group)

    if preferred_engine in valid:
        reference_bpm = float(valid[preferred_engine]["bpm"])
        winning_group = [
            name for name in names
            if abs(float(valid[name]["bpm"]) - reference_bpm) <= tolerance
        ]
        consensus_bpm = float(np.median([
            float(valid[name]["bpm"]) for name in winning_group
        ]))
        selection_strategy = "validated_metrical_reference_v1"
    else:
        largest = max(len(group) for group in groups)
        candidates = [group for group in groups if len(group) == largest]
        candidates.sort(key=lambda group: (
            -sum(name in group for name in ("all_in_one", "essentia")),
            [names.index(name) for name in group],
        ))
        winning_group = candidates[0]
        consensus_bpm = float(np.median([
            float(valid[name]["bpm"]) for name in winning_group
        ]))
        selection_strategy = "degraded_exact_value_group"
    has_majority = len(winning_group) >= 2

    engine_priority = {"beat_this": 0, "all_in_one": 1, "essentia": 2}
    selected_engine = min(
        winning_group,
        key=lambda name: (
            abs(float(valid[name]["bpm"]) - consensus_bpm),
            engine_priority.get(name, 99),
        ),
    )
    available_count = len(valid)
    status = (
        "unanimous" if has_majority and len(winning_group) == available_count == 3
        else "majority" if has_majority and available_count == 3
        else "degraded_agreement" if has_majority
        else "no_majority"
    )
    tempo_hypotheses = sorted({
        round(float(value["bpm"]) * ratio, 3)
        for value in valid.values()
        for ratio in (0.5, 2.0 / 3.0, 1.0, 1.5, 2.0)
        if 30.0 <= float(value["bpm"]) * ratio <= 300.0
    })
    alias_relations = []
    alias_ratios = {
        "half": 0.5, "two_thirds": 2.0 / 3.0, "same": 1.0,
        "three_halves": 1.5, "double": 2.0,
    }
    for index, left_name in enumerate(names):
        for right_name in names[index + 1:]:
            left = float(valid[left_name]["bpm"])
            right = float(valid[right_name]["bpm"])
            relation, ratio = min(
                alias_ratios.items(), key=lambda item: abs(left * item[1] - right)
            )
            error = abs(left * ratio - right)
            if error <= tolerance:
                alias_relations.append({
                    "engines": [left_name, right_name],
                    "relation": relation,
                    "ratio": round(ratio, 6),
                    "error_bpm": round(error, 4),
                })
    return {
        "bpm": consensus_bpm,
        "selected_engine": selected_engine,
        "winning_engines": winning_group,
        "agreement_count": len(winning_group),
        "available_count": available_count,
        "status": status,
        "needs_review": not has_majority or available_count < 3,
        "selection_strategy": selection_strategy,
        "metrical_reference_engine": preferred_engine if preferred_engine in valid else None,
        "tolerance": float(tolerance),
        "votes": {name: round(float(value["bpm"]), 3) for name, value in valid.items()},
        "tempo_hypotheses": tempo_hypotheses,
        "alias_relations": alias_relations,
        "metrical_level_conflict": any(
            item["relation"] != "same" for item in alias_relations
        ),
    }


def _analyze_rhythm_parallel(
    y: np.ndarray,
    sr: int,
    *,
    max_duration: float | None = None,
    file_path: str | os.PathLike[str] | None = None,
) -> tuple[dict, dict, dict]:
    """Run Beat This, All-In-One, and Essentia concurrently and vote on BPM."""
    jobs = {}
    if _env_flag("BPM_ENABLE_BEAT_THIS"):
        jobs["beat_this"] = lambda: _analyze_rhythm_beat_this(y, sr)
    if _env_flag("BPM_ENABLE_ALL_IN_ONE"):
        if file_path is None:
            jobs["all_in_one"] = lambda: _analyze_rhythm_all_in_one(y, sr)
        else:
            jobs["all_in_one"] = lambda: _analyze_rhythm_all_in_one(
                y, sr, file_path=file_path,
            )
    if _env_flag("BPM_ENABLE_ESSENTIA"):
        jobs["essentia"] = lambda: _analyze_rhythm_essentia(y, sr, max_duration=max_duration)
    if not jobs:
        raise ValueError("all BPM engines are disabled")
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="bpm-engine") as executor:
        futures = {executor.submit(job): name for name, job in jobs.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                errors[name] = f"{type(exc).__name__}: {exc}"

    consensus = _choose_bpm_consensus(results, tolerance=_bpm_consensus_tolerance())
    consensus["errors"] = errors
    from app.modules.library.tempo_model_validation import resolve_tempo_model_validation
    consensus["model_validation"] = resolve_tempo_model_validation(consensus, results)
    selected = results[consensus["selected_engine"]]
    return selected, consensus, results


def _analyze_key(y: np.ndarray, sr: int) -> dict:
    """Comprehensive key detection with cross-validation, candidates, and tonal clarity.

    Uses two chroma representations (CQT + CENS) with Krumhansl-Schmuckler template
    matching, then cross-validates to produce a confidence-weighted result.

    Returns:
        key, camelot_key, key_confidence, candidates (top 3), tonal_clarity,
        relative_ambiguity, method
    """
    import librosa

    if len(y) < sr:
        return {
            "key": "C major", "camelot_key": "8B",
            "key_confidence": 0.0, "tonal_clarity": 0.0,
            "relative_ambiguity": False, "candidates": [],
            "method": "fallback_short_audio",
        }

    # ── 1. CQT Chroma (standard, wide-band) ──────────────────────────
    try:
        chroma_cqt = librosa.feature.chroma_cqt(y=y, sr=sr, bins_per_octave=24)
        cqt_profile = np.mean(chroma_cqt, axis=1)
        if len(cqt_profile) == 12:
            chroma_12 = np.asarray(cqt_profile, dtype=float)
        elif len(cqt_profile) >= 24:
            chroma_12 = np.asarray(cqt_profile[:12] + cqt_profile[12:24], dtype=float)
        else:
            chroma_12 = np.zeros(12, dtype=float)
    except Exception:
        chroma_12 = np.zeros(12, dtype=float)

    # ── 2. CENS Chroma (noise-robust, timbre-invariant) ──────────────
    try:
        chroma_cens = librosa.feature.chroma_cens(y=y, sr=sr)
        cens_profile = np.mean(chroma_cens, axis=1)
    except Exception:
        cens_profile = np.zeros(12, dtype=float)

    # ── 3. Tonal clarity: how "peaky" is the chroma distribution ─────
    def _tonal_clarity(profile: np.ndarray) -> float:
        if np.sum(profile) <= 1e-9:
            return 0.0
        p = profile / (np.sum(profile) + 1e-9)
        # Entropy-based: low entropy = clear tonality (one note dominates)
        entropy = -np.sum(p * np.log(p + 1e-9)) / np.log(12)
        return float(np.clip(1.0 - entropy, 0.0, 1.0))

    cqt_clarity = _tonal_clarity(chroma_12)
    cens_clarity = _tonal_clarity(cens_profile)
    tonal_clarity = round(float(np.clip(cqt_clarity * 0.6 + cens_clarity * 0.4, 0.0, 1.0)), 4)

    # ── 4. K-S template matching on both chromas ─────────────────────
    def _match_templates(profile: np.ndarray) -> list[dict]:
        if np.sum(profile) <= 1e-9:
            return [{"root": "C", "mode": "major", "camelot": "8B", "score": 0.0}]
        prof = profile / (np.linalg.norm(profile) + 1e-9)
        results = []
        for idx, note in enumerate(NOTE_NAMES):
            for template, m in [(MAJOR_TEMPLATE, "major"), (MINOR_TEMPLATE, "minor")]:
                rotated = np.roll(template, idx)
                rotated = rotated / (np.linalg.norm(rotated) + 1e-9)
                score = float(np.dot(prof, rotated))
                results.append({
                    "root": note, "mode": m,
                    "camelot": NOTE_MODE_TO_CAMELOT[(note, m)],
                    "score": round(max(0.0, min(1.0, score)), 4),
                })
        results.sort(key=lambda r: -r["score"])
        return results

    cqt_results = _match_templates(chroma_12)
    cens_results = _match_templates(cens_profile)

    # ── 5. Cross-validate: weighted consensus ────────────────────────
    key_scores: dict[tuple[str, str], float] = {}  # (root, mode) → weighted score
    for i, r in enumerate(cqt_results):
        w = 0.6 * (1.0 / (i + 1))  # rank-weighted, CQT weight 0.6
        k = (r["root"], r["mode"])
        key_scores[k] = key_scores.get(k, 0.0) + w * r["score"]
    for i, r in enumerate(cens_results):
        w = 0.4 * (1.0 / (i + 1))  # rank-weighted, CENS weight 0.4
        k = (r["root"], r["mode"])
        key_scores[k] = key_scores.get(k, 0.0) + w * r["score"]

    ranked = sorted(key_scores.items(), key=lambda kv: -kv[1])
    if not ranked:
        return {
            "key": "C major", "camelot_key": "8B",
            "key_confidence": 0.0, "tonal_clarity": 0.0,
            "relative_ambiguity": False, "candidates": [],
            "method": "fallback_no_match",
        }

    # ── 6. Build candidates with cross-validated scores ──────────────
    max_score = ranked[0][1] if ranked else 1.0
    candidates = []
    for (root, mode), score in ranked[:6]:
        candidates.append({
            "root": root, "mode": mode,
            "camelot": NOTE_MODE_TO_CAMELOT[(root, mode)],
            "score": round(score / (max_score + 1e-9), 4),
        })

    best = candidates[0]
    key_confidence = round(float(np.clip(best["score"] * 0.7 + tonal_clarity * 0.3, 0.0, 1.0)), 4)

    # ── 7. Relative ambiguity detection ──────────────────────────────
    # Check if the relative major/minor is a close second
    # e.g., C major ↔ A minor (same notes, different tonal center)
    relative_ambiguity = False
    if len(candidates) >= 2:
        best_key = (best["root"], best["mode"])
        for c in candidates[1:4]:
            other_key = (c["root"], c["mode"])
            # Same set of notes = relative major/minor
            best_idx = NOTE_NAMES.index(best["root"])
            other_idx = NOTE_NAMES.index(c["root"])
            semitone_diff = (other_idx - best_idx) % 12
            # Relative minor is 3 semitones down from major (or 9 up)
            # Relative major is 3 semitones up from minor (or 9 down)
            is_relative = (best["mode"] == "major" and c["mode"] == "minor" and semitone_diff == 9) or \
                          (best["mode"] == "minor" and c["mode"] == "major" and semitone_diff == 3)
            if is_relative and c["score"] > 0.7:
                relative_ambiguity = True
                break

    # ── 8. Determine method ──────────────────────────────────────────
    cqt_best = cqt_results[0] if cqt_results else None
    cens_best = cens_results[0] if cens_results else None
    if cqt_best and cens_best and \
       cqt_best["root"] == cens_best["root"] and cqt_best["mode"] == cens_best["mode"]:
        method = "ks_cqt_cens_agree"
    else:
        method = "ks_cqt_cens_weighted"

    return {
        "key": f"{best['root']} {best['mode']}",
        "camelot_key": best["camelot"],
        "key_confidence": key_confidence,
        "tonal_clarity": tonal_clarity,
        "relative_ambiguity": relative_ambiguity,
        "candidates": candidates[:3],
        "method": method,
    }


def _build_bpm_curve(
    beat_times: list[float] | np.ndarray,
    *,
    window_beats: int = 16,
    hop_beats: int = 8,
) -> tuple[list[dict], float]:
    """Summarize local tempo and report how stable the beat grid is."""
    beats = np.asarray(beat_times, dtype=float)
    if len(beats) < 3:
        return [], 0.0

    intervals = np.diff(beats)
    intervals = intervals[(intervals > 0.15) & (intervals < 2.5)]
    if len(intervals) < 2:
        return [], 0.0

    window = max(2, min(int(window_beats), len(intervals)))
    hop = max(1, int(hop_beats))
    starts = list(range(0, max(len(intervals) - window + 1, 1), hop))
    last_start = max(0, len(intervals) - window)
    if not starts or starts[-1] != last_start:
        starts.append(last_start)

    curve: list[dict] = []
    for start in starts:
        chunk = intervals[start:start + window]
        median_interval = float(np.median(chunk))
        mean_interval = float(np.mean(chunk))
        if median_interval <= 1e-9 or mean_interval <= 1e-9:
            continue
        local_stability = float(np.clip(1.0 - np.std(chunk) / mean_interval, 0.0, 1.0))
        curve.append({
            "start": round(float(beats[start]), 3),
            "end": round(float(beats[min(start + window, len(beats) - 1)]), 3),
            "bpm": round(60.0 / median_interval, 2),
            "stability": round(local_stability, 4),
        })

    if not curve:
        return [], 0.0

    local_mean = float(np.mean([item["stability"] for item in curve]))
    local_bpms = np.asarray([item["bpm"] for item in curve], dtype=float)
    median_bpm = float(np.median(local_bpms))
    tempo_consistency = (
        float(np.clip(1.0 - np.std(local_bpms) / median_bpm, 0.0, 1.0))
        if median_bpm > 1e-9 else 0.0
    )
    stability = float(np.clip(local_mean * 0.6 + tempo_consistency * 0.4, 0.0, 1.0))
    return curve, round(stability, 4)


def _summarize_beatgrid(
    beat_times: list[float] | np.ndarray,
    bpm_curve: list[dict],
    tempo_stability: float,
) -> dict:
    """Describe whether a beat grid is reliable enough for phrase-aligned mixing."""
    beats = np.asarray(beat_times, dtype=float)
    valid_intervals = np.diff(beats)
    valid_intervals = valid_intervals[(valid_intervals > 0.15) & (valid_intervals < 2.5)]
    if len(valid_intervals) == 0:
        interval = 0.0
        offset = float(beats[0]) if len(beats) else 0.0
        phase_consistency = 0.0
    else:
        interval = float(np.median(valid_intervals))
        offset = float(beats[0] % interval) if interval > 1e-9 else 0.0
        local_deviation = float(np.mean(np.abs(valid_intervals - interval)))
        phase_consistency = float(np.clip(1.0 - local_deviation / interval * 4.0, 0.0, 1.0))

    count_confidence = float(np.clip(len(beats) / 64.0, 0.0, 1.0))
    curve_confidence = float(np.clip(len(bpm_curve) / 4.0, 0.0, 1.0))
    confidence = float(np.clip(
        float(tempo_stability) * 0.50
        + phase_consistency * 0.30
        + count_confidence * 0.15
        + curve_confidence * 0.05,
        0.0,
        1.0,
    ))
    needs_review = confidence < 0.72 or len(beats) < 16 or interval <= 1e-9
    return {
        "beat_confidence": round(confidence, 4),
        "beat_confidence_details": {
            "tempo_stability": round(float(tempo_stability), 4),
            "phase_consistency": round(phase_consistency, 4),
            "beat_count_confidence": round(count_confidence, 4),
            "curve_confidence": round(curve_confidence, 4),
        },
        "beat_grid_offset": round(offset, 4),
        "beat_grid_interval": round(interval, 4),
        "beat_engines_used": ["librosa"],
        "beat_needs_review": bool(needs_review),
    }


def _build_energy_curve(
    y: np.ndarray,
    sr: int,
    *,
    window_sec: float = 2.0,
    hop_sec: float = 1.0,
) -> list[dict]:
    """Build a compact loudness contour for energy-aware phrase selection."""
    if sr <= 0 or len(y) == 0:
        return []

    mono = np.asarray(y, dtype=float)
    if mono.ndim > 1:
        mono = np.mean(mono, axis=0)
    frame_length = max(1, int(sr * window_sec))
    hop_length = max(1, int(sr * hop_sec))
    if len(mono) < frame_length:
        frame_length = len(mono)

    rms_values: list[tuple[int, int, float]] = []
    for start in range(0, max(len(mono) - frame_length + 1, 1), hop_length):
        end = min(start + frame_length, len(mono))
        chunk = mono[start:end]
        rms = float(np.sqrt(np.mean(np.square(chunk)))) if len(chunk) else 0.0
        rms_values.append((start, end, rms))

    if not rms_values:
        return []
    peak_rms = max(item[2] for item in rms_values) or 1.0
    return [{
        "start": round(start / sr, 3),
        "end": round(end / sr, 3),
        "energy": round(float(np.clip(np.tanh(rms * 8.0), 0.0, 1.0)), 4),
        "relative_energy": round(float(np.clip(rms / peak_rms, 0.0, 1.0)), 4),
    } for start, end, rms in rms_values]


def _analyze_loudness(
    y: np.ndarray,
    sr: int,
    *,
    target_lufs: float = -14.0,
    peak_headroom_db: float = 1.0,
) -> dict:
    """Measure playback loudness and derive a conservative replay gain."""
    audio = np.asarray(y, dtype=float)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=0)
    audio = audio.reshape(-1)

    if sr <= 0 or len(audio) == 0:
        audio = np.zeros(1, dtype=float)

    abs_audio = np.abs(audio)
    peak = float(np.max(abs_audio))
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if peak <= 1e-9 or rms <= 1e-9:
        return {
            "integrated_lufs": None,
            "loudness_method": "silence",
            "peak_dbfs": None,
            "rms_dbfs": None,
            "crest_factor_db": 0.0,
            "clip_ratio": 0.0,
            "replay_gain_db": 0.0,
            "clipping_risk": False,
        }

    peak_dbfs = 20.0 * np.log10(peak)
    rms_dbfs = 20.0 * np.log10(rms)
    loudness_method = "rms_dbfs_fallback"
    integrated_lufs = rms_dbfs
    try:
        import pyloudnorm as pyln

        measured = float(pyln.Meter(sr).integrated_loudness(audio))
        if np.isfinite(measured):
            integrated_lufs = measured
            loudness_method = "ebu_r128"
    except Exception:
        pass

    clip_ratio = float(np.mean(abs_audio >= 0.999))
    target_gain = float(target_lufs - integrated_lufs)
    max_gain_with_headroom = float(-peak_headroom_db - peak_dbfs)
    replay_gain = min(target_gain, max_gain_with_headroom)
    replay_gain = float(np.clip(replay_gain, -12.0, 12.0))
    clipping_risk = clip_ratio > 0.00001 or peak_dbfs >= -0.1

    return {
        "integrated_lufs": round(float(integrated_lufs), 3),
        "loudness_method": loudness_method,
        "peak_dbfs": round(float(peak_dbfs), 3),
        "rms_dbfs": round(float(rms_dbfs), 3),
        "crest_factor_db": round(float(peak_dbfs - rms_dbfs), 3),
        "clip_ratio": round(clip_ratio, 6),
        "replay_gain_db": round(replay_gain, 3),
        "clipping_risk": bool(clipping_risk),
    }


def _attach_phrase_energy(phrase_map: list[dict], energy_curve: list[dict]) -> list[dict]:
    """Attach average relative energy to phrase windows without mutating input."""
    enriched: list[dict] = []
    for phrase in phrase_map:
        item = dict(phrase)
        start = float(item.get("start", 0.0))
        end = float(item.get("end", start))
        values = [
            float(window.get("relative_energy", window.get("energy", 0.0)))
            for window in energy_curve
            if float(window.get("start", 0.0)) < end
            and float(window.get("end", window.get("start", 0.0))) > start
        ]
        if values:
            item["energy"] = round(float(np.mean(values)), 4)
        enriched.append(item)
    return enriched


def _build_transition_windows(phrase_map: list[dict]) -> list[dict]:
    """Score phrase-sized windows for safe mix-in and mix-out decisions."""
    role_scores = {
        "intro": (0.92, 0.35),
        "verse": (0.68, 0.58),
        "buildup": (0.45, 0.72),
        "drop": (0.52, 0.48),
        "breakdown": (0.74, 0.80),
        "outro": (0.30, 0.94),
    }
    windows: list[dict] = []
    for phrase in phrase_map:
        label = str(phrase.get("label", "verse")).lower()
        mix_in, mix_out = role_scores.get(label, (0.55, 0.55))
        energy = float(phrase.get("energy", 0.5))
        bars = int(phrase.get("bars", 0) or 0)
        if energy < 0.45:
            mix_in += 0.06
            mix_out += 0.04
        if energy > 0.82:
            mix_in -= 0.08
            mix_out -= 0.06
        if bars and bars < 4:
            mix_in -= 0.08
            mix_out -= 0.08
        clean_candidate = label in {"intro", "breakdown", "outro"} and energy <= 0.55
        windows.append({
            "start": round(float(phrase.get("start", 0.0)), 3),
            "end": round(float(phrase.get("end", phrase.get("start", 0.0))), 3),
            "label": label,
            "bars": bars,
            "energy": round(energy, 4),
            "mix_in_score": round(float(np.clip(mix_in, 0.0, 1.0)), 4),
            "mix_out_score": round(float(np.clip(mix_out, 0.0, 1.0)), 4),
            "clean_candidate": clean_candidate,
        })
    return windows


def camelot_distance(key_a: str, key_b: str) -> int:
    """
    Compute the Camelot Wheel distance between two keys.
    Returns 0 for perfect match, 1 for adjacent (harmonic), 2 for energy boost, 7+ for clash.
    """
    if not key_a or not key_b:
        return 99
    try:
        num_a, mode_a = int(key_a[:-1]), key_a[-1]
        num_b, mode_b = int(key_b[:-1]), key_b[-1]
    except (ValueError, IndexError):
        return 99
    if num_a == num_b and mode_a == mode_b:
        return 0  # same key
    if num_a == num_b and mode_a != mode_b:
        return 1  # relative major/minor
    if mode_a == mode_b:
        diff = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
        return diff
    # Cross-mode non-same-number
    diff = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
    return diff + 1


def camelot_score(key_a: str, key_b: str) -> int:
    """Score 0-100 for harmonic compatibility on the Camelot Wheel."""
    d = camelot_distance(key_a, key_b)
    if d == 0:
        return 100
    if d == 1:
        return 80
    if d == 2:
        return 60
    if d == 3:
        return 30
    return 0


def _functional_segments_to_cues(
    segments: list[dict] | None,
    *,
    source: str = "songformer_functional_segment",
) -> list[dict]:
    """Convert model segments without relabelling them from energy or position."""
    colors = {
        "start": "#22c55e", "intro": "#22c55e", "verse": "#3b82f6",
        "chorus": "#ef4444", "bridge": "#f59e0b", "break": "#a855f7",
        "inst": "#06b6d4", "instrumental": "#06b6d4",
        "solo": "#14b8a6", "outro": "#64748b",
        "pre-chorus": "#f97316",
        "end": "#64748b",
    }
    cues = []
    for segment in segments or []:
        try:
            start = max(0.0, float(segment["start"]))
            end = max(start, float(segment["end"]))
            contract = enrich_section_segment(segment, source=source)
            label = str(contract["structure_label_candidate"]).strip().lower()
        except (KeyError, TypeError, ValueError):
            continue
        if label:
            cues.append({
                "time": round(start, 3),
                "end": round(end, 3),
                "label": label.title(),
                "raw_label": contract.get("songformer_label") or label,
                "color": colors.get(label, "#64748b"),
                "source": source,
                **{
                    key: contract.get(key)
                    for key in SECTION_CONTRACT_FIELDS
                },
            })
    return cues


def _functional_segments_to_phrase_map(
    segments: list[dict] | None,
    downbeats: list[float] | None = None,
    *,
    source: str = "songformer_functional_segment",
) -> list[dict]:
    """Expose authoritative functional sections as the product phrase map.

    Explicit ``start``/``end`` markers are metadata rather than musical
    sections and are omitted.  All other boundaries and labels are preserved;
    energy and intensity may be attached later but cannot move a boundary or
    change a label.
    """
    grid = sorted({round(float(value), 6) for value in (downbeats or [])})
    phrases: list[dict] = []
    for segment in segments or []:
        try:
            start = max(0.0, float(segment["start"]))
            end = max(start, float(segment["end"]))
            contract = enrich_section_segment(segment, source=source)
            label = str(contract["structure_label_candidate"]).strip().lower()
        except (KeyError, TypeError, ValueError):
            continue
        if not label or label in {"start", "end"} or end <= start:
            continue
        phrases.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "label": label,
            "raw_label": contract.get("songformer_label") or label,
            "bars": sum(start - 0.1 <= value < end - 0.1 for value in grid),
            "source": source,
            **{
                key: contract.get(key)
                for key in SECTION_CONTRACT_FIELDS
            },
        })
    return phrases


def _functional_intro_end(segments: list[dict] | None) -> tuple[float, dict]:
    """Return the end of the leading authoritative-model intro region.

    Some tracks have only a short ``start`` marker and no explicit ``intro``.
    In that case the marker end is the best available origin; if neither is
    present, bar numbering starts from the first available downbeat.
    """
    parsed: list[tuple[float, float, str]] = []
    for segment in segments or []:
        try:
            start = max(0.0, float(segment["start"]))
            end = max(start, float(segment["end"]))
            label = str(segment["label"]).strip().lower()
        except (KeyError, TypeError, ValueError):
            continue
        if label and end > start:
            parsed.append((start, end, label))
    parsed.sort(key=lambda item: (item[0], item[1]))

    marker_end = 0.0
    intro_end = 0.0
    intro_detected = False
    cursor = 0.0
    for start, end, label in parsed:
        if start > cursor + 0.25:
            break
        if label == "start":
            marker_end = max(marker_end, end)
            cursor = max(cursor, end)
            continue
        if label == "intro":
            intro_detected = True
            intro_end = max(intro_end, end)
            cursor = max(cursor, end)
            continue
        break

    if intro_detected:
        origin = intro_end
        reason = "leading_intro_end"
    elif marker_end > 0.0:
        origin = marker_end
        reason = "start_marker_end_no_intro_label"
    else:
        origin = 0.0
        reason = "no_intro_label"
    return round(origin, 4), {
        "intro_detected": intro_detected,
        "intro_end": round(origin, 4),
        "origin_reason": reason,
    }


def _start_bar_grid_after_intro(
    downbeats: list[float] | None,
    segments: list[dict] | None,
    *,
    beat_times: list[float] | np.ndarray | None = None,
    beats_per_bar: int = 4,
    boundary_tolerance: float = 0.1,
) -> tuple[list[float], dict]:
    """Number bars from the first detected downbeat after the model intro.

    Once the first strong beat is located, subsequent bar starts are counted
    every ``beats_per_bar`` beat ticks.  This prevents a downbeat model that
    emits occasional half-bars or double-bars from changing bar numbering in
    the middle of a song.
    """
    raw_grid = sorted({round(float(value), 3) for value in (downbeats or [])})
    intro_end, intro_meta = _functional_intro_end(segments)
    if not segments:
        return [], {
            **intro_meta,
            "status": "functional_sections_unavailable",
            "rule": "first_downbeat_at_or_after_functional_intro_end",
            "raw_downbeat_count": len(raw_grid),
            "removed_intro_downbeats": len(raw_grid),
            "first_bar_downbeat": None,
        }
    if not raw_grid:
        return [], {
            **intro_meta,
            "status": "downbeats_unavailable",
            "rule": "first_downbeat_at_or_after_functional_intro_end",
            "raw_downbeat_count": 0,
            "removed_intro_downbeats": 0,
            "first_bar_downbeat": None,
        }

    first_index = next((
        index for index, value in enumerate(raw_grid)
        if value >= intro_end - max(0.0, float(boundary_tolerance))
    ), len(raw_grid))
    candidate_grid = raw_grid[first_index:]
    product_grid = candidate_grid
    grid_mode = "native_downbeats_after_intro"
    anchor_beat_index = None
    meter = max(1, int(beats_per_bar or 4))
    beat_values = list(beat_times) if beat_times is not None else []
    beats = sorted({round(float(value), 6) for value in beat_values})
    if candidate_grid and beats:
        anchor = candidate_grid[0]
        anchor_beat_index = min(range(len(beats)), key=lambda index: abs(beats[index] - anchor))
        intervals = np.diff(np.asarray(beats, dtype=float))
        median_interval = float(np.median(intervals)) if len(intervals) else 0.0
        snap_tolerance = max(0.1, median_interval * 0.55)
        if abs(beats[anchor_beat_index] - anchor) <= snap_tolerance:
            product_grid = [
                round(float(value), 3)
                for value in beats[anchor_beat_index::meter]
            ]
            grid_mode = "counted_beats_from_first_post_intro_downbeat"
    return product_grid, {
        **intro_meta,
        "status": "ok" if product_grid else "no_downbeat_after_intro",
        "rule": "first_downbeat_at_or_after_functional_intro_end",
        "boundary_tolerance_seconds": round(max(0.0, float(boundary_tolerance)), 3),
        "raw_downbeat_count": len(raw_grid),
        "removed_intro_downbeats": first_index,
        "first_bar_downbeat": product_grid[0] if product_grid else None,
        "grid_mode": grid_mode,
        "beats_per_bar": meter,
        "anchor_beat_index": anchor_beat_index,
        "first_bar_offset_from_intro_end": (
            round(product_grid[0] - intro_end, 4) if product_grid else None
        ),
    }


def _infer_downbeats_and_time_signature(
    beat_times: list[float] | np.ndarray,
    beat_strengths: list[float] | np.ndarray,
) -> tuple[list[float], dict]:
    """Infer bar meter and downbeat phase from per-beat accent strengths."""
    beats = np.asarray(beat_times, dtype=float)
    strengths = np.asarray(beat_strengths, dtype=float)
    usable = min(len(beats), len(strengths))
    if usable < 8:
        downbeats = [round(float(beats[0]), 3)] if len(beats) else []
        return downbeats, {
            "numerator": 4,
            "denominator": 4,
            "confidence": 0.0,
            "candidates": [{"numerator": 4, "denominator": 4, "score": 0.0}],
            "method": "fallback",
            "needs_review": True,
        }

    beats = beats[:usable]
    strengths = strengths[:usable]
    scale = float(np.max(strengths) - np.min(strengths))
    if scale <= 1e-9:
        normalized = np.zeros_like(strengths)
    else:
        normalized = (strengths - np.min(strengths)) / scale

    candidates: list[dict] = []
    for numerator in (4, 3, 6, 2):
        best_phase = 0
        best_score = -1.0
        for phase in range(numerator):
            accent_mask = np.arange(usable) % numerator == phase
            accent_mean = float(np.mean(normalized[accent_mask]))
            other_mean = float(np.mean(normalized[~accent_mask])) if np.any(~accent_mask) else 0.0
            contrast = float(np.clip(accent_mean - other_mean, 0.0, 1.0))
            support = float(np.clip(np.sum(accent_mask) / 8.0, 0.0, 1.0))
            score = contrast * 0.85 + support * 0.15
            if numerator == 4:
                score += 0.015
            if score > best_score:
                best_score = score
                best_phase = phase
        candidates.append({
            "numerator": numerator,
            "denominator": 4,
            "score": round(float(np.clip(best_score, 0.0, 1.0)), 4),
            "phase": best_phase,
        })

    candidates.sort(key=lambda item: item["score"], reverse=True)
    best = candidates[0]
    if float(best["score"]) < 0.45:
        raw_best = best
        best = next(item for item in candidates if item["numerator"] == 4)
        numerator = 4
        phase = int(best["phase"])
        downbeats = [
            round(float(beats[index]), 3)
            for index in range(phase, len(beats), numerator)
        ]
        return downbeats, {
            "numerator": 4,
            "denominator": 4,
            "confidence": round(float(best["score"]), 4),
            "candidates": candidates[:3],
            "method": "beat_accent_periodicity_fallback_4_4",
            "needs_review": True,
            "raw_best_numerator": int(raw_best["numerator"]),
        }
    numerator = int(best["numerator"])
    phase = int(best["phase"])
    downbeats = [
        round(float(beats[index]), 3)
        for index in range(phase, len(beats), numerator)
    ]
    return downbeats, {
        "numerator": numerator,
        "denominator": int(best["denominator"]),
        "confidence": round(float(best["score"]), 4),
        "candidates": candidates[:3],
        "method": "beat_accent_periodicity",
        "needs_review": False,
    }


def _detect_downbeats_with_meter(
    y: np.ndarray,
    sr: int,
    beat_times: np.ndarray,
) -> tuple[list[float], dict]:
    """
    Detect downbeats and meter from the same beat-accent evidence.
    """
    import librosa

    if len(beat_times) < 4:
        downbeats = [round(float(beat_times[0]), 3)] if len(beat_times) > 0 else []
        return downbeats, {
            "numerator": 4,
            "denominator": 4,
            "confidence": 0.0,
            "candidates": [{"numerator": 4, "denominator": 4, "score": 0.0}],
            "method": "fallback",
            "needs_review": True,
        }

    # Compute onset strength at each beat position
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    hop = 512
    beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=hop)
    beat_frames = np.clip(beat_frames, 0, len(onset_env) - 1)
    beat_strengths = onset_env[beat_frames]

    return _infer_downbeats_and_time_signature(beat_times, beat_strengths)


def _detect_downbeats(y: np.ndarray, sr: int, beat_times: np.ndarray) -> list[float]:
    """Compatibility wrapper for callers that only need bar boundaries."""
    downbeats, _time_signature = _detect_downbeats_with_meter(y, sr, beat_times)
    return downbeats


def _downbeat_match_metrics(
    first: list[float] | np.ndarray,
    second: list[float] | np.ndarray,
    *,
    tolerance: float = DOWNBEAT_MATCH_TOLERANCE_SECONDS,
) -> dict:
    """Return one-to-one downbeat matching metrics within a time tolerance."""
    left = np.asarray(first, dtype=float)
    right = np.asarray(second, dtype=float)
    left = np.sort(left[np.isfinite(left)])
    right = np.sort(right[np.isfinite(right)])
    if len(left) == 0 or len(right) == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "matches": 0, "mean_error_ms": None}

    used: set[int] = set()
    errors: list[float] = []
    for value in left:
        candidates = np.where(np.abs(right - value) <= tolerance)[0]
        candidates = [int(index) for index in candidates if int(index) not in used]
        if not candidates:
            continue
        index = min(candidates, key=lambda item: abs(float(right[item] - value)))
        used.add(index)
        errors.append(abs(float(right[index] - value)))
    matches = len(errors)
    precision = matches / len(left)
    recall = matches / len(right)
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "matches": matches,
        "mean_error_ms": round(float(np.mean(errors) * 1000.0), 2) if errors else None,
    }


def _downbeat_period_profile(
    values: list[float] | np.ndarray,
    *,
    bpm: float | None,
    beats_per_bar: int,
    period_tolerance: float,
    max_intro_bars: float,
) -> dict:
    points = np.asarray(values, dtype=float)
    points = np.sort(points[np.isfinite(points)])
    intervals = np.diff(points)
    median_period = float(np.median(intervals)) if len(intervals) else None
    expected_period = (
        float(beats_per_bar * 60.0 / bpm)
        if bpm is not None and np.isfinite(bpm) and bpm > 0 and beats_per_bar > 0
        else None
    )
    ratio = (
        float(median_period / expected_period)
        if median_period is not None and expected_period is not None and expected_period > 0
        else None
    )
    compatible = ratio is None or abs(ratio - 1.0) <= period_tolerance
    issue = None
    if ratio is not None and not compatible:
        aliases = {
            "half_bar": 0.5,
            "two_thirds_bar": 2.0 / 3.0,
            "three_halves_bar": 1.5,
            "double_bar": 2.0,
        }
        issue, alias_ratio = min(aliases.items(), key=lambda item: abs(ratio - item[1]))
        if abs(ratio - alias_ratio) > period_tolerance:
            issue = "period_mismatch"
    first_downbeat = float(points[0]) if len(points) else None
    intro_coverage_ok = (
        True
        if first_downbeat is None or expected_period is None
        else first_downbeat <= expected_period * max_intro_bars
    )
    return {
        "median_period_seconds": round(median_period, 4) if median_period is not None else None,
        "expected_period_seconds": round(expected_period, 4) if expected_period is not None else None,
        "period_ratio": round(ratio, 4) if ratio is not None else None,
        "compatible": bool(compatible),
        "issue": issue,
        "first_downbeat_seconds": round(first_downbeat, 4) if first_downbeat is not None else None,
        "intro_coverage_ok": bool(intro_coverage_ok),
    }


def _downbeat_phase_metrics(
    first: list[float] | np.ndarray,
    second: list[float] | np.ndarray,
    *,
    bpm: float | None,
    beats_per_bar: int,
    tolerance: float,
    period_tolerance: float,
) -> dict:
    left = np.asarray(first, dtype=float)
    right = np.asarray(second, dtype=float)
    left = np.sort(left[np.isfinite(left)])
    right = np.sort(right[np.isfinite(right)])
    if bpm is None or bpm <= 0 or len(left) < 2 or len(right) < 2:
        return {"is_phase_conflict": False, "shift_seconds": None, "shift_beats": None}

    periods = [float(np.median(np.diff(values))) for values in (left, right)]
    period = float(np.mean(periods))
    expected_period = float(beats_per_bar * 60.0 / bpm)
    if period <= 0 or abs(period / expected_period - 1.0) > period_tolerance:
        return {"is_phase_conflict": False, "shift_seconds": None, "shift_beats": None}

    # The first stable phrase carries the clearest bar phase. Later breakdowns
    # can make a model emit extra half-bars and hide an otherwise obvious
    # integer-beat phase shift when taking a whole-song median.
    def circular_phase(values: np.ndarray) -> float:
        angles = 2.0 * np.pi * values[:12] / period
        mean_angle = float(np.angle(np.mean(np.exp(1j * angles))))
        return (mean_angle % (2.0 * np.pi)) * period / (2.0 * np.pi)

    left_phase = circular_phase(left)
    right_phase = circular_phase(right)
    shift_seconds = abs((right_phase - left_phase + period / 2.0) % period - period / 2.0)
    beat_seconds = 60.0 / bpm
    shift_beats = int(round(shift_seconds / beat_seconds))
    residual = abs(shift_seconds - shift_beats * beat_seconds)
    is_conflict = bool(
        shift_seconds > tolerance
        and 1 <= shift_beats < beats_per_bar
        and residual <= max(tolerance, beat_seconds * 0.2)
    )
    return {
        "is_phase_conflict": is_conflict,
        "shift_seconds": round(shift_seconds, 4),
        "shift_beats": shift_beats if is_conflict else None,
    }


def _choose_downbeat_consensus(
    results: dict[str, dict],
    *,
    accent_fallback: list[float],
    tolerance: float = DOWNBEAT_MATCH_TOLERANCE_SECONDS,
    agreement_f1: float = DOWNBEAT_AGREEMENT_F1,
    preferred_engine: str = "all_in_one",
    bpm: float | None = None,
    beats_per_bar: int = 4,
    period_tolerance: float = DOWNBEAT_PERIOD_TOLERANCE,
    max_intro_bars: float = DOWNBEAT_MAX_INTRO_BARS,
) -> tuple[list[float], dict]:
    """Choose a validated downbeat route, or a reviewable multi-route fallback."""
    native_valid = {
        name: value for name, value in results.items()
        if len(value.get("downbeats") or []) >= 2
    }
    priority = {"all_in_one": 0, "beat_this": 1, "madmom": 2}
    period_validation = {
        name: _downbeat_period_profile(
            value["downbeats"],
            bpm=bpm,
            beats_per_bar=beats_per_bar,
            period_tolerance=period_tolerance,
            max_intro_bars=max_intro_bars,
        )
        for name, value in native_valid.items()
    }
    valid = {
        name: value for name, value in native_valid.items()
        if period_validation[name]["compatible"]
    }
    names = sorted(valid, key=lambda name: priority.get(name, 99))
    all_names = sorted(native_valid, key=lambda name: priority.get(name, 99))
    pair_metrics: dict[str, dict] = {}
    agreeing_pairs: set[frozenset[str]] = set()
    phase_conflicts: dict[str, dict] = {}
    for index, first_name in enumerate(all_names):
        for second_name in all_names[index + 1:]:
            metrics = _downbeat_match_metrics(
                native_valid[first_name]["downbeats"],
                native_valid[second_name]["downbeats"],
                tolerance=tolerance,
            )
            pair_metrics[f"{first_name}:{second_name}"] = metrics
            pair_is_eligible = first_name in valid and second_name in valid
            if pair_is_eligible and float(metrics["f1"]) >= agreement_f1:
                agreeing_pairs.add(frozenset((first_name, second_name)))
            elif pair_is_eligible:
                phase = _downbeat_phase_metrics(
                    native_valid[first_name]["downbeats"],
                    native_valid[second_name]["downbeats"],
                    bpm=bpm,
                    beats_per_bar=beats_per_bar,
                    tolerance=tolerance,
                    period_tolerance=period_tolerance,
                )
                if phase["is_phase_conflict"]:
                    phase_conflicts[f"{first_name}:{second_name}"] = phase

    groups: list[list[str]] = []
    for mask in range(1, 1 << len(names)):
        group = [names[index] for index in range(len(names)) if mask & (1 << index)]
        if len(group) == 1 or all(
            frozenset((group[left], group[right])) in agreeing_pairs
            for left in range(len(group)) for right in range(left + 1, len(group))
        ):
            groups.append(group)

    available_count = len(native_valid)
    eligible_count = len(valid)
    winning_group = max(
        groups,
        key=lambda group: (
            len(group),
            preferred_engine in group,
            -sum(priority.get(name, 99) for name in group),
        ),
        default=[],
    )
    has_model_agreement = len(winning_group) >= 2
    accent_metrics = {
        name: _downbeat_match_metrics(value["downbeats"], accent_fallback, tolerance=tolerance)
        for name, value in native_valid.items()
    }

    # A route may bypass heuristic voting only when its exact model,
    # postprocessor and per-track confidence gate match held-out validation.
    # Low-confidence output still participates as a provisional route.
    validated_reference = next((
        name
        for name in ([preferred_engine] + [item for item in all_names if item != preferred_engine])
        if name in native_valid
        and bool((native_valid[name].get("model_validation") or {}).get("downbeat_validated"))
    ), None)

    def selection_rank(name: str) -> tuple:
        profile = period_validation[name]
        return (
            bool(profile["intro_coverage_ok"]),
            float(accent_metrics[name]["f1"]),
            float(native_valid[name].get("confidence", 0.0)),
            -priority.get(name, 99),
        )

    def agreement_rank(name: str) -> tuple:
        profile = period_validation[name]
        return (
            bool(profile["intro_coverage_ok"]),
            name == preferred_engine,
            float(accent_metrics[name]["f1"]),
            float(native_valid[name].get("confidence", 0.0)),
            -priority.get(name, 99),
        )

    if validated_reference is not None:
        selected_engine = validated_reference
        status = "validated_reference"
        needs_review = False
        if not winning_group or selected_engine not in winning_group:
            winning_group = [selected_engine]
        coverage_override = False
    elif has_model_agreement:
        selected_engine = max(winning_group, key=agreement_rank)
        coverage_override = selected_engine != min(
            winning_group, key=lambda name: priority.get(name, 99)
        )
        status = (
            "unanimous" if len(winning_group) == eligible_count == available_count == 3
            else "majority" if available_count == 3
            else "degraded_agreement"
        )
        needs_review = bool(
            available_count < 3
            or eligible_count < available_count
            or coverage_override
            or any(not period_validation[name]["intro_coverage_ok"] for name in winning_group)
        )
    elif names:
        accent_winner = max(
            names,
            key=selection_rank,
        )
        selected_engine = accent_winner
        winning_group = [selected_engine]
        if phase_conflicts:
            status = "phase_conflict"
        elif eligible_count < available_count:
            status = "period_filtered"
        elif float(accent_metrics[accent_winner]["f1"]) >= agreement_f1:
            status = "accent_tiebreak"
        else:
            status = "no_majority"
        needs_review = True
    else:
        fallback_status = "period_fallback" if native_valid else "fallback"
        return list(accent_fallback), {
            "selected_engine": "accent_fallback",
            "winning_engines": [],
            "agreement_count": 0,
            "available_count": available_count,
            "eligible_count": 0,
            "status": fallback_status,
            "needs_review": True,
            "tolerance_ms": round(tolerance * 1000.0, 2),
            "agreement_f1_threshold": agreement_f1,
            "period_tolerance": period_tolerance,
            "expected_bar_period_seconds": (
                round(float(beats_per_bar * 60.0 / bpm), 4) if bpm is not None and bpm > 0 else None
            ),
            "period_validation": period_validation,
            "rejected_engines": all_names,
            "phase_conflicts": phase_conflicts,
            "pair_metrics": pair_metrics,
            "accent_metrics": accent_metrics,
        }

    selected = [round(float(value), 3) for value in native_valid[selected_engine]["downbeats"]]
    return selected, {
        "selected_engine": selected_engine,
        "selected_engine_name": native_valid[selected_engine].get("engine"),
        "winning_engines": winning_group,
        "agreement_count": len(winning_group),
        "available_count": available_count,
        "eligible_count": eligible_count,
        "status": status,
        "needs_review": needs_review,
        "tolerance_ms": round(tolerance * 1000.0, 2),
        "agreement_f1_threshold": agreement_f1,
        "period_tolerance": period_tolerance,
        "expected_bar_period_seconds": (
            round(float(beats_per_bar * 60.0 / bpm), 4) if bpm is not None and bpm > 0 else None
        ),
        "period_validation": period_validation,
        "rejected_engines": [name for name in all_names if name not in valid],
        "phase_conflicts": phase_conflicts,
        "pair_metrics": pair_metrics,
        "accent_metrics": accent_metrics,
        "model_confidences": {
            name: round(float(value.get("confidence", 0.0)), 4)
            for name, value in native_valid.items()
        },
        "model_validations": {
            name: value.get("model_validation")
            for name, value in native_valid.items() if value.get("model_validation")
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Extended analysis: time signature, section intensity, groove, vocal events,
# bass risk, stem-aware transition scoring.
# ═══════════════════════════════════════════════════════════════════════════════


def _detect_time_signature(
    beat_times: list[float] | np.ndarray,
    downbeat_times: list[float],
    *,
    bpm: float = 0.0,
) -> dict:
    """Detect time signature by measuring beats between consecutive downbeats.

    Returns {numerator, denominator, confidence, candidates}.
    """
    beats = np.asarray(beat_times, dtype=float)
    downs = np.asarray(downbeat_times, dtype=float)

    if len(downs) < 3 or len(beats) < 8:
        return {
            "numerator": 4, "denominator": 4,
            "confidence": 0.0,
            "candidates": [{"numerator": 4, "denominator": 4, "score": 0.0}],
            "method": "fallback",
        }

    # Count beats between consecutive downbeats
    bar_beat_counts: list[int] = []
    for i in range(len(downs) - 1):
        count = int(np.sum((beats >= downs[i]) & (beats < downs[i + 1])))
        if count > 0:
            bar_beat_counts.append(count)

    if not bar_beat_counts:
        return {
            "numerator": 4, "denominator": 4,
            "confidence": 0.0,
            "candidates": [],
            "method": "empty",
        }

    values, counts = np.unique(bar_beat_counts, return_counts=True)
    total = len(bar_beat_counts)

    # Check common signatures: 4, 3, 6, 5, 7 beats per bar
    candidates = []
    for num in [4, 3, 6, 5, 7, 2, 8]:
        idx = np.where(values == num)[0]
        if len(idx) > 0:
            match_pct = float(counts[idx][0]) / total
            # Bonus: if this matches the downbeat detection's implied signature
            phase_bonus = 0.0
            if num == 4:
                phase_bonus = 0.10  # slight prior for 4/4 (most dance music)
            score = float(np.clip(match_pct + phase_bonus, 0.0, 1.0))
            candidates.append({"numerator": int(num), "denominator": 4, "score": round(score, 4)})

    candidates.sort(key=lambda c: -c["score"])

    # Also check for 6/8 (compound: 2 beats per bar with triplet feel)
    if bpm > 0 and len(beats) >= 16:
        intervals = np.diff(beats)
        intervals = intervals[(intervals > 0.15) & (intervals < 2.5)]
        if len(intervals) >= 8:
            median_beat = float(np.median(intervals))
            # In 6/8, the "beat" is dotted quarter, so librosa might report it as
            # either the dotted quarter (slow) or eighth note (fast).
            # If median beat is very fast (<0.25s → >240bpm equivalent), might be 6/8
            if median_beat < 0.22:
                candidates.append({"numerator": 6, "denominator": 8, "score": 0.4})

    if not candidates:
        candidates = [{"numerator": 4, "denominator": 4, "score": 0.0}]

    best = candidates[0]
    confidence = best["score"] if best["score"] >= 0.6 else float(np.clip(best["score"] * 1.3, 0.0, 0.55))

    return {
        "numerator": best["numerator"],
        "denominator": best["denominator"],
        "confidence": round(confidence, 4),
        "candidates": candidates[:3],
        "method": "bar_beat_histogram",
    }


def _score_section_intensity(
    phrase_map: list[dict],
    energy_curve: list[dict],
    y: np.ndarray | None = None,
    sr: int = 22050,
) -> list[dict]:
    """Score structural sections by energy dynamics and spectral contrast.

    Adds 'intensity' (0-1), 'energy_range', 'is_peak_section', 'is_valley_section'
    to each phrase entry.
    """
    if not phrase_map:
        return phrase_map

    # Collect all phrase energies for relative ranking
    energies = np.array([float(p.get("energy", 0.5)) for p in phrase_map])
    median_e = float(np.median(energies)) if len(energies) else 0.5
    max_e = float(energies.max()) if len(energies) else 1.0

    # Per-phrase energy range from energy_curve
    phrase_ranges: list[float] = []
    for p in phrase_map:
        p_start = float(p.get("start", 0))
        p_end = float(p.get("end", p_start))
        vals = [
            float(w.get("relative_energy", w.get("energy", 0.0)))
            for w in energy_curve
            if float(w.get("start", 0)) < p_end and float(w.get("end", 0)) > p_start
        ]
        if vals and len(vals) >= 2:
            phrase_ranges.append(float(np.max(vals) - np.min(vals)))
        else:
            phrase_ranges.append(0.0)

    max_range = max(phrase_ranges) if phrase_ranges else 1.0

    # Spectral contrast per phrase (if audio available)
    spectral_contrasts: list[float] = []
    if y is not None and sr > 0 and len(y) >= sr:
        try:
            import librosa
            S = np.abs(librosa.stft(np.asarray(y, dtype=float).flatten()))
            for p in phrase_map:
                p_start = max(0, int(float(p.get("start", 0)) * sr / 512))
                p_end = min(S.shape[1], int(float(p.get("end", p.get("start", 0))) * sr / 512))
                if p_end > p_start + 1:
                    band_means = np.mean(S[:, p_start:p_end], axis=1)
                    if len(band_means) >= 6:
                        spectral_contrasts.append(float(np.std(band_means) / (np.mean(band_means) + 1e-8)))
                    else:
                        spectral_contrasts.append(0.0)
                else:
                    spectral_contrasts.append(0.0)
        except Exception:
            spectral_contrasts = [0.0] * len(phrase_map)
    else:
        spectral_contrasts = [0.0] * len(phrase_map)

    max_contrast = max(spectral_contrasts) if spectral_contrasts else 1.0

    enriched: list[dict] = []
    for i, p in enumerate(phrase_map):
        item = dict(p)
        e = float(p.get("energy", 0.5))
        r = phrase_ranges[i] if i < len(phrase_ranges) else 0.0
        sc = spectral_contrasts[i] if i < len(spectral_contrasts) else 0.0

        # Intensity = weighted combo of absolute energy + range + spectral contrast
        intensity = float(np.clip(
            (e / (max_e + 1e-8)) * 0.45
            + (r / (max_range + 1e-8)) * 0.30
            + (sc / (max_contrast + 1e-8)) * 0.25,
            0.0, 1.0,
        ))
        item["intensity"] = round(intensity, 4)
        item["energy_range"] = round(r, 4)
        if sc > 0:
            item["spectral_variation"] = round(sc, 4)
        # Lower thresholds when spectral data unavailable (intensity capped at ~0.45)
        has_spectral = max_contrast > 1e-8
        peak_intensity_threshold = 0.55 if has_spectral else 0.4
        valley_intensity_threshold = 0.45 if has_spectral else 0.5
        item["is_peak_section"] = bool(e >= max_e * 0.85 and intensity >= peak_intensity_threshold)
        item["is_valley_section"] = bool(e <= max(median_e * 0.8, 0.15) and intensity <= valley_intensity_threshold)
        enriched.append(item)

    return enriched


def _compute_groove_score(
    beat_times: list[float] | np.ndarray,
    downbeat_times: list[float],
    bpm_curve: list[dict],
    tempo_stability: float,
) -> dict:
    """Compute a DJ-oriented 'groove' score: how reliably danceable the rhythm is.

    Returns {score, breakdown: {steady_beat, syncopation, downbeat_clarity, tempo_lock}}.
    High score = consistent beat + moderate syncopation + clear downbeats.
    """
    beats = np.asarray(beat_times, dtype=float)
    downs = np.asarray(downbeat_times, dtype=float)

    if len(beats) < 16:
        return {
            "score": 0.0,
            "breakdown": {"steady_beat": 0.0, "syncopation": 0.0,
                          "downbeat_clarity": 0.0, "tempo_lock": 0.0},
            "method": "insufficient_data",
        }

    # 1. Steady beat: how consistent are inter-beat intervals
    ibi = np.diff(beats)
    ibi = ibi[(ibi > 0.15) & (ibi < 2.5)]
    if len(ibi) >= 8:
        median_ibi = float(np.median(ibi))
        ibi_cv = float(np.std(ibi) / (median_ibi + 1e-6))  # coefficient of variation
        steady_beat = float(np.clip(1.0 - ibi_cv * 2.5, 0.0, 1.0))
    else:
        steady_beat = 0.0

    # 2. Syncopation: moderate variation in beat intervals (not perfectly metronomic, not chaotic)
    #    DJs want some "feel" — groove_complexity from the feature extractor
    if len(ibi) >= 8:
        odd = ibi[0::2]; even = ibi[1::2]
        n = min(len(odd), len(even))
        if n >= 2:
            swing = float(np.clip(
                1.0 - abs(float(odd[:n].mean() / (even[:n].mean() + 1e-6)) - 1.0) * 4.0,
                0.0, 1.0,
            ))
        else:
            swing = 0.5
        # Syncopation sweet spot: some variation but not chaotic
        groove_complexity = float(np.clip(ibi_cv * 5.0, 0.0, 1.0))
        syncopation = float(np.clip(groove_complexity * 0.5 + swing * 0.5, 0.0, 1.0))
    else:
        syncopation = 0.5

    # 3. Downbeat clarity: how consistently spaced are downbeats
    if len(downs) >= 4:
        dbi = np.diff(downs)
        dbi = dbi[(dbi > 0.3) & (dbi < 8.0)]
        if len(dbi) >= 3:
            dbi_cv = float(np.std(dbi) / (np.mean(dbi) + 1e-6))
            downbeat_clarity = float(np.clip(1.0 - dbi_cv * 2.0, 0.0, 1.0))
        else:
            downbeat_clarity = 0.3
    else:
        downbeat_clarity = 0.0

    # 4. Tempo lock: from bpm_curve stability + tempo_stability
    tempo_lock = float(tempo_stability) if tempo_stability else steady_beat * 0.6

    # Combined groove score
    score = float(np.clip(
        steady_beat * 0.30
        + syncopation * 0.30
        + downbeat_clarity * 0.22
        + tempo_lock * 0.18,
        0.0, 1.0,
    ))

    label = "stiff" if (steady_beat > 0.9 and syncopation < 0.3) else \
            "loose" if steady_beat < 0.4 else \
            "groovy" if score >= 0.65 else \
            "steady" if score >= 0.4 else \
            "unstable"

    return {
        "score": round(score, 4),
        "label": label,
        "breakdown": {
            "steady_beat": round(steady_beat, 4),
            "syncopation": round(syncopation, 4),
            "downbeat_clarity": round(downbeat_clarity, 4),
            "tempo_lock": round(tempo_lock, 4),
        },
        "method": "rhythm_statistical",
    }


def _analyze_dancefloor_profile(
    *,
    bpm: float,
    energy: float,
    groove: dict | None,
    stem_activity: dict | None = None,
    spectral_centroid: float | None = None,
    phrase_map: list[dict] | None = None,
) -> dict:
    """Summarize how a track feels on a dance floor, with explainable factors."""
    groove = groove or {}
    stems = stem_activity or {}
    groove_score = float(np.clip(groove.get("score", 0.5), 0.0, 1.0))
    drums = float(np.clip(stems.get("drums", groove_score), 0.0, 1.0))
    bass = float(np.clip(stems.get("bass", energy), 0.0, 1.0))
    vocals = float(np.clip(stems.get("vocals", 0.35), 0.0, 1.0))
    brightness = float(np.clip(((spectral_centroid or 2200.0) - 900.0) / 3200.0, 0.0, 1.0))
    tempo_fit = float(np.clip(1.0 - abs(float(bpm) - 115.0) / 80.0, 0.0, 1.0))
    peak_intensity = max(
        [float(item.get("intensity", item.get("energy", 0.0))) for item in (phrase_map or [])]
        or [float(energy)]
    )

    danceability = float(np.clip(
        groove_score * 0.45 + drums * 0.20 + bass * 0.12
        + tempo_fit * 0.15 + peak_intensity * 0.08,
        0.0, 1.0,
    ))
    physical_energy = float(np.clip(
        float(energy) * 0.50 + drums * 0.25 + bass * 0.20 + peak_intensity * 0.05,
        0.0, 1.0,
    ))
    tension = float(np.clip(
        float(energy) * 0.35 + brightness * 0.20 + vocals * 0.15 + peak_intensity * 0.30,
        0.0, 1.0,
    ))
    fatigue_risk = float(np.clip(
        float(energy) * 0.35
        + np.clip((float(bpm) - 105.0) / 80.0, 0.0, 1.0) * 0.25
        + brightness * 0.20 + drums * 0.20,
        0.0, 1.0,
    ))

    mood_tags: list[str] = []
    if physical_energy >= 0.70:
        mood_tags.append("driving")
    if tension >= 0.72:
        mood_tags.append("tense")
    if groove_score >= 0.68:
        mood_tags.append("groovy")
    if physical_energy <= 0.40:
        mood_tags.append("laid_back")
    if brightness >= 0.65:
        mood_tags.append("bright")
    if brightness <= 0.25:
        mood_tags.append("dark")
    if vocals >= 0.60:
        mood_tags.append("vocal_led")
    if not mood_tags:
        mood_tags.append("balanced")

    return {
        "danceability_score": round(danceability, 4),
        "danceability_label": (
            "high" if danceability >= 0.72
            else "medium" if danceability >= 0.48
            else "low"
        ),
        "physical_energy": round(physical_energy, 4),
        "tension": round(tension, 4),
        "peakness": round(float(np.clip(peak_intensity, 0.0, 1.0)), 4),
        "fatigue_risk": round(fatigue_risk, 4),
        "mood_tags": mood_tags,
        "breakdown": {
            "groove": round(groove_score, 4),
            "drums": round(drums, 4),
            "bass": round(bass, 4),
            "vocals": round(vocals, 4),
            "brightness": round(brightness, 4),
            "tempo_fit": round(tempo_fit, 4),
        },
        "method": "explainable_audio_features",
    }


def _detect_vocal_events(
    stem_activity_windows: list[dict],
    *,
    entry_threshold: float = 0.35,
    exit_threshold: float = 0.25,
    min_gap_sec: float = 2.0,
) -> list[dict]:
    """Detect vocal enter/exit events from stem activity windows.

    Each event: {time, type: "enter"|"exit", confidence, vocal_level}.
    """
    if not stem_activity_windows:
        return []

    events: list[dict] = []
    was_active = False

    for i, w in enumerate(stem_activity_windows):
        vocal = float(w.get("vocals", 0.0))
        t = float(w.get("start", 0.0))

        if not was_active and vocal >= entry_threshold:
            # Vocal enters
            peak_idx = i
            peak_val = vocal
            for j in range(i, min(i + 4, len(stem_activity_windows))):
                v = float(stem_activity_windows[j].get("vocals", 0.0))
                if v > peak_val:
                    peak_val = v
                    peak_idx = j
            events.append({
                "time": round(float(stem_activity_windows[peak_idx].get("start", t)), 2),
                "type": "enter",
                "confidence": round(min(1.0, vocal / 0.7), 3),
                "vocal_level": round(vocal, 3),
            })
            was_active = True

        elif was_active and vocal <= exit_threshold:
            # Vocal exits — confirm with next windows
            confirmed = True
            for j in range(i + 1, min(i + 3, len(stem_activity_windows))):
                if float(stem_activity_windows[j].get("vocals", 0.0)) > exit_threshold:
                    confirmed = False
                    break
            if confirmed:
                events.append({
                    "time": round(t, 2),
                    "type": "exit",
                    "confidence": round(min(1.0, (exit_threshold - vocal) / exit_threshold), 3),
                    "vocal_level": round(vocal, 3),
                })
                was_active = False

    # Deduplicate: merge events closer than min_gap_sec
    if len(events) >= 2:
        merged: list[dict] = [events[0]]
        for e in events[1:]:
            last = merged[-1]
            if (e["time"] - last["time"]) < min_gap_sec and e["type"] == last["type"]:
                # Keep the one with higher confidence
                if e["confidence"] > last["confidence"]:
                    merged[-1] = e
            else:
                merged.append(e)
        events = merged

    return events


def _compute_bass_risk_windows(
    stem_activity_windows: list[dict],
    *,
    heavy_threshold: float = 0.55,
) -> list[dict]:
    """Tag windows where bass is dominant → potential cross-song bass conflict.

    Returns per-window bass risk info: {start, end, bass_level, bass_dominance, risk}.
    """
    if not stem_activity_windows:
        return []

    windows: list[dict] = []
    for w in stem_activity_windows:
        bass = float(w.get("bass", 0.0))
        drums = float(w.get("drums", 0.0))
        vocals = float(w.get("vocals", 0.0))
        other = float(w.get("other", 0.0))
        total = bass + drums + vocals + other
        if total <= 1e-8:
            continue

        bass_dominance = bass / total
        is_heavy = bass > heavy_threshold
        risk = "high" if is_heavy and bass_dominance > 0.4 else \
               "medium" if is_heavy else \
               "low"

        windows.append({
            "start": float(w.get("start", 0.0)),
            "end": float(w.get("end", 0.0)),
            "bass_level": round(bass, 4),
            "bass_dominance": round(bass_dominance, 4),
            "risk": risk,
        })
    return windows


def _enhance_transition_windows(
    transition_windows: list[dict],
    stem_activity_windows: list[dict],
) -> list[dict]:
    """Add stem-aware scores to transition windows: tag vocal-free, drum-heavy, bass-solo.

    Adjusts mix_in_score and mix_out_score using real stem activity data.
    """
    if not transition_windows:
        return transition_windows

    # Build stem activity index for fast lookup
    def _stem_for_range(start: float, end: float) -> dict:
        vocals_vals: list[float] = []
        drums_vals: list[float] = []
        bass_vals: list[float] = []
        other_vals: list[float] = []
        for w in stem_activity_windows:
            ws = float(w.get("start", 0))
            we = float(w.get("end", ws + 2))
            if ws < end and we > start:
                vocals_vals.append(float(w.get("vocals", 0)))
                drums_vals.append(float(w.get("drums", 0)))
                bass_vals.append(float(w.get("bass", 0)))
                other_vals.append(float(w.get("other", 0)))
        return {
            "vocals": float(np.mean(vocals_vals)) if vocals_vals else 0.0,
            "drums": float(np.mean(drums_vals)) if drums_vals else 0.0,
            "bass": float(np.mean(bass_vals)) if bass_vals else 0.0,
            "other": float(np.mean(other_vals)) if other_vals else 0.0,
        }

    enhanced: list[dict] = []
    for tw in transition_windows:
        item = dict(tw)
        t_start = float(tw.get("start", 0))
        t_end = float(tw.get("end", t_start + 8))
        stem = _stem_for_range(t_start, t_end) if stem_activity_windows else {}

        # Stem tags
        tags: list[str] = []
        if stem.get("vocals", 0.5) < 0.2:
            tags.append("vocal_free")
        if stem.get("drums", 0.5) > 0.5:
            tags.append("drum_heavy")
        if stem.get("bass", 0.5) > 0.55:
            tags.append("bass_heavy")
        if stem.get("bass", 0.5) < 0.2 and stem.get("drums", 0.5) < 0.2:
            tags.append("ambient")
        if stem.get("vocals", 0.5) > 0.5:
            tags.append("vocal_led")
        if stem.get("drums", 0.5) > 0.5 and stem.get("vocals", 0.5) < 0.15 and stem.get("bass", 0.5) < 0.25:
            tags.append("drum_solo")
        item["stem_tags"] = tags

        # Store stem activity snapshot
        item["stem_snapshot"] = {
            k: round(v, 3) for k, v in stem.items()
        } if stem else {}

        # Adjust scores based on stem data
        mix_in = float(item.get("mix_in_score", 0.5))
        mix_out = float(item.get("mix_out_score", 0.5))

        if "vocal_free" in tags:
            mix_in += 0.10  # clean entry point
        if "drum_heavy" in tags:
            mix_in += 0.06  # good rhythmic anchor for incoming track
            mix_out += 0.04  # good rhythmic anchor for outgoing
        if "bass_heavy" in tags:
            mix_in -= 0.08  # bass conflict risk
            mix_out -= 0.06
        if "ambient" in tags:
            mix_out += 0.12  # easy to fade out
            mix_in -= 0.04  # weak entry
        if "vocal_led" in tags:
            mix_in -= 0.10  # vocal clash if incoming has vocals
            mix_out -= 0.08  # hard to exit during vocals

        item["mix_in_score"] = round(float(np.clip(mix_in, 0.0, 1.0)), 4)
        item["mix_out_score"] = round(float(np.clip(mix_out, 0.0, 1.0)), 4)

        # Clean candidate refined with stem data
        label = str(item.get("label", "")).lower()
        has_vocal_free = "vocal_free" in tags
        has_drums = stem.get("drums", 0) > 0.25
        energy = float(item.get("energy", 0.5))
        if label in ("intro", "breakdown", "outro"):
            item["clean_candidate"] = bool(has_vocal_free and has_drums and energy <= 0.6)
        else:
            item["clean_candidate"] = bool(item.get("clean_candidate", False))

        enhanced.append(item)

    return enhanced


def _recommend_transition_techniques(
    phrase_map: list[dict],
    transition_windows: list[dict],
    stem_activity_windows: list[dict] | None = None,
) -> list[dict]:
    """For each phrase section, recommend the best transition presets.

    Returns a list of transition recommendations, one per phrase, each with:
      - time range
      - section label
      - best MIX-IN presets (B enters here)
      - best MIX-OUT presets (A exits here)
      - overall recommendation type (entry_point, exit_point, both, avoid)

    The logic encodes DJ knowledge about which structural positions work
    with which transition techniques.
    """
    if not phrase_map:
        return []

    # ── Preset categories for recommendation ──────────────────────────
    IN_PRESETS_BY_ROLE = {
        "clean_entry":   ["fade", "neural_fade", "melt"],
        "rhythm_entry":  ["filter_sweep", "eq_bass_swap", "wave"],
        "energy_entry":  ["riser", "breakdown_drop", "hard_cut"],
        "ambient_entry": ["dissolve", "lunar_echo", "harmonic_sustain"],
        "dramatic_entry":["hydrant", "sweep", "neural_echo_out"],
    }
    OUT_PRESETS_BY_ROLE = {
        "clean_exit":    ["fade", "melt", "neural_fade"],
        "echo_exit":     ["echo_freeze", "lunar_echo", "neural_echo_out"],
        "energy_exit":   ["riser", "hydrant", "sweep"],
        "ambient_exit":  ["dissolve", "tremolo", "harmonic_sustain"],
        "cut_exit":      ["hard_cut", "breakdown_drop", "eq_bass_swap"],
    }

    # ── Score a window for each role ───────────────────────────────────
    def _score_role(window: dict, role: str, direction: str) -> float:
        """Score 0-1 how well this window fits a given role."""
        label = str(window.get("label", "")).lower()
        energy = float(window.get("energy", 0.5))
        intensity = float(window.get("intensity", energy))
        is_peak = bool(window.get("is_peak_section", False))
        is_valley = bool(window.get("is_valley_section", False))
        clean = bool(window.get("clean_candidate", False))
        stem_tags = window.get("stem_tags", [])

        score = 0.3  # baseline

        if role == "clean_entry":
            if label in ("intro",):        score += 0.4
            if clean:                       score += 0.2
            if "vocal_free" in stem_tags:   score += 0.15
            if energy < 0.5:                score += 0.1

        elif role == "rhythm_entry":
            if label in ("intro", "buildup"): score += 0.25
            if "drum_heavy" in stem_tags:    score += 0.3
            if energy > 0.4:                 score += 0.15

        elif role == "energy_entry":
            if is_peak:                      score += 0.35
            if label in ("drop", "buildup"): score += 0.3
            if intensity > 0.6:             score += 0.15

        elif role == "ambient_entry":
            if is_valley:                    score += 0.3
            if label in ("breakdown",):      score += 0.35
            if energy < 0.4:                score += 0.15

        elif role == "dramatic_entry":
            if is_peak:                      score += 0.3
            if energy > 0.7:                score += 0.2
            if label in ("drop",):           score += 0.2

        # ── Direction adjustments ──
        if direction == "out":
            if role == "clean_exit":
                if label in ("outro",):         score += 0.4
                if energy < 0.45:               score += 0.15
                if "vocal_free" in stem_tags:   score += 0.1
            elif role == "echo_exit":
                if label in ("outro", "breakdown", "verse"): score += 0.25
                if "vocal_led" in stem_tags:    score += 0.2
            elif role == "energy_exit":
                if is_peak:                      score += 0.35
                if intensity > 0.65:            score += 0.2
            elif role == "ambient_exit":
                if is_valley:                    score += 0.3
                if label in ("breakdown",):      score += 0.3
            elif role == "cut_exit":
                if label in ("drop", "outro"):   score += 0.2
                if energy > 0.6:                score += 0.15

        return float(min(1.0, score))

    # ── Build recommendations per window ───────────────────────────────
    recommendations: list[dict] = []
    windows = transition_windows if transition_windows else phrase_map

    for i, w in enumerate(windows):
        start = float(w.get("start", 0))
        end = float(w.get("end", start + 8))
        label = str(w.get("label", "?"))
        energy = float(w.get("energy", 0.5))

        # Score all roles
        in_scores = {role: _score_role(w, role, "in") for role in IN_PRESETS_BY_ROLE}
        out_scores = {role: _score_role(w, role, "out") for role in OUT_PRESETS_BY_ROLE}

        # Pick top 2 roles for each direction
        top_in = sorted(in_scores.items(), key=lambda x: -x[1])[:2]
        top_out = sorted(out_scores.items(), key=lambda x: -x[1])[:2]

        # Collect recommended presets
        in_presets: list[dict] = []
        for role, score in top_in:
            if score < 0.4:
                continue
            for p in IN_PRESETS_BY_ROLE[role][:2]:
                if not any(x["preset"] == p for x in in_presets):
                    in_presets.append({"preset": p, "role": role, "score": round(score, 3)})

        out_presets: list[dict] = []
        for role, score in top_out:
            if score < 0.4:
                continue
            for p in OUT_PRESETS_BY_ROLE[role][:2]:
                if not any(x["preset"] == p for x in out_presets):
                    out_presets.append({"preset": p, "role": role, "score": round(score, 3)})

        # Determine recommendation type
        best_in_score = top_in[0][1] if top_in else 0.0
        best_out_score = top_out[0][1] if top_out else 0.0

        if best_in_score > 0.55 and best_out_score > 0.55:
            rec_type = "both"
        elif best_in_score > 0.55:
            rec_type = "entry_point"
        elif best_out_score > 0.55:
            rec_type = "exit_point"
        elif best_in_score < 0.3 and best_out_score < 0.3:
            rec_type = "avoid"
        else:
            rec_type = "neutral"

        # Position context
        rel_pos = start / max(float(phrase_map[-1].get("end", 1)) if phrase_map else 1, 1)
        if rel_pos < 0.12:
            position = "beginning"
        elif rel_pos > 0.85:
            position = "ending"
        elif 0.3 < rel_pos < 0.7:
            position = "middle"
        else:
            position = "transition_zone"

        recommendations.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "label": label,
            "energy": round(energy, 3),
            "position": position,
            "type": rec_type,
            "best_for_mix_in": in_presets[:4],
            "best_for_mix_out": out_presets[:4],
            "role_scores_in": {k: round(v, 3) for k, v in sorted(in_scores.items(), key=lambda x: -x[1]) if v > 0.25},
            "role_scores_out": {k: round(v, 3) for k, v in sorted(out_scores.items(), key=lambda x: -x[1]) if v > 0.25},
        })

    return recommendations


MAX_ANALYSIS_DURATION = 420.0  # 7 min cap — sufficient for BPM/key/energy; prevents OOM on long mixes


def analyze_audio_file(file_path: str, *, title: str | None = None, artist: str | None = None, **_kwargs) -> dict:
    """Full analysis: BPM, beat points, downbeats, key, camelot key, energy, cue points, phrase map, duration.

    `title` / `artist` are accepted for forward-compatibility with callers that
    pass song metadata (used by future genre/style classifiers); currently ignored.
    """
    import librosa
    import soundfile as sf

    # Get real file duration from metadata (no audio decode) so we always report true length
    try:
        real_duration = float(sf.info(file_path).duration)
    except Exception:
        real_duration = None

    y, sr = librosa.load(file_path, sr=22050, duration=MAX_ANALYSIS_DURATION)
    # Duration used for analysis-relative positioning (capped)
    analysis_duration = float(librosa.get_duration(y=y, sr=sr))
    # Reported duration = real file length when available
    duration = real_duration if real_duration is not None else analysis_duration

    # SongFormer is deliberately isolated from the rhythm family: it owns only
    # functional sections, and it runs first so its temporary encoder models
    # are released before All-In-One or the beat/downbeat models use memory.
    songformer_route: dict[str, Any] | None = None
    songformer_error: str | None = None
    if _env_flag("SECTION_ENABLE_SONGFORMER", True):
        try:
            songformer_route = _analyze_sections_songformer(file_path)
        except Exception as exc:
            songformer_error = f"{type(exc).__name__}: {exc}"
    else:
        songformer_error = "SongFormer section analysis is disabled"

    # BPM + beat points. Beat This, All-In-One, and the existing Essentia route
    # Run independent rhythm routes concurrently. The held-out-validated Beat
    # This route fixes the BPM metrical level; same-level routes only smooth
    # its measurement. Librosa remains the final degraded fallback.
    rhythm_result: dict[str, Any] | None = None
    rhythm_results: dict[str, dict] = {}
    bpm_consensus: dict[str, Any] | None = None
    rhythm_fallback_reason: str | None = None
    madmom_result: dict[str, Any] | None = None
    madmom_error: str | None = None
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="rhythm-family") as executor:
        rhythm_future = executor.submit(
            _analyze_rhythm_parallel,
            y,
            sr,
            max_duration=MAX_ANALYSIS_DURATION,
            file_path=file_path,
        )
        madmom_future = (
            executor.submit(_analyze_downbeats_madmom, y, sr)
            if _env_flag("DOWNBEAT_ENABLE_MADMOM") else None
        )
        try:
            rhythm_result, bpm_consensus, rhythm_results = rhythm_future.result()
            bpm = float(bpm_consensus["bpm"])
            beat_times = np.asarray(rhythm_result["beat_times"], dtype=float)
        except Exception as exc:
            rhythm_fallback_reason = f"{type(exc).__name__}: {exc}"
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            bpm = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        if madmom_future is not None:
            try:
                madmom_result = madmom_future.result()
            except Exception as exc:
                madmom_error = f"{type(exc).__name__}: {exc}"

    if rhythm_result is None and rhythm_fallback_reason is None:
        # Defensive guard for unexpected future orchestration changes.
        rhythm_fallback_reason = "rhythm consensus returned no selected engine"
    beat_points = [round(float(t), 3) for t in beat_times]
    bpm_curve, tempo_stability = _build_bpm_curve(beat_times)
    beatgrid_summary = _summarize_beatgrid(beat_times, bpm_curve, tempo_stability)
    if rhythm_result is not None:
        beatgrid_summary["beat_engines_used"] = [
            rhythm_results[name]["engine"] for name in ("beat_this", "all_in_one", "essentia")
            if name in rhythm_results
        ]
        details = dict(beatgrid_summary.get("beat_confidence_details") or {})
        details.update({
            "selected_bpm_engine": rhythm_result["engine"],
            "selected_engine_confidence": round(float(rhythm_result.get("confidence", 0.0)), 4),
            "bpm_candidates": rhythm_result.get("bpm_candidates", []),
            "bpm_intervals": rhythm_result.get("bpm_intervals", []),
            "method": rhythm_result.get("method"),
            "sample_rate": rhythm_result.get("sample_rate"),
            "bpm_consensus": bpm_consensus,
        })
        beatgrid_summary["beat_confidence_details"] = details
        beatgrid_summary["beat_confidence"] = round(float(np.clip(
            float(beatgrid_summary.get("beat_confidence") or 0.0) * 0.7
            + float(rhythm_result.get("confidence") or 0.0) * 0.3,
            0.0,
            1.0,
        )), 4)
        beatgrid_summary["beat_needs_review"] = bool(
            beatgrid_summary.get("beat_confidence", 0.0) < 0.72
            or len(beat_points) < 16
            or bool((bpm_consensus or {}).get("needs_review"))
        )
    else:
        beatgrid_summary["beat_engines_used"] = ["librosa_fallback"]
        details = dict(beatgrid_summary.get("beat_confidence_details") or {})
        details["fallback_reason"] = rhythm_fallback_reason
        beatgrid_summary["beat_confidence_details"] = details

    # Native downbeats are voted independently from BPM. The local beat-accent
    # route is intentionally only a tie-break/fallback.
    accent_downbeats, accent_time_signature = _detect_downbeats_with_meter(y, sr, beat_times)
    downbeat_results = {
        name: rhythm_results[name]
        for name in ("beat_this", "all_in_one")
        if name in rhythm_results and rhythm_results[name].get("downbeats")
    }
    if madmom_result is not None:
        downbeat_results["madmom"] = madmom_result
    raw_downbeats, downbeat_consensus = _choose_downbeat_consensus(
        downbeat_results,
        accent_fallback=accent_downbeats,
        tolerance=_downbeat_match_tolerance(),
        agreement_f1=_downbeat_agreement_f1(),
        bpm=bpm,
        beats_per_bar=int(accent_time_signature.get("numerator", 4) or 4),
        period_tolerance=_downbeat_period_tolerance(),
        max_intro_bars=_downbeat_max_intro_bars(),
    )
    all_in_one_route = rhythm_results.get("all_in_one") or {}
    functional_segments, section_selection = _select_authoritative_sections(
        songformer_route,
        all_in_one_route,
        songformer_error=songformer_error,
    )
    intro_end_candidate, intro_end_details = _functional_intro_end(
        functional_segments
    )
    downbeat_consensus["errors"] = ({"madmom": madmom_error} if madmom_error else {})
    time_signature = _detect_time_signature(beat_times, raw_downbeats, bpm=bpm)
    downbeats, bar_grid_origin = _start_bar_grid_after_intro(
        raw_downbeats,
        functional_segments,
        beat_times=beat_times,
        beats_per_bar=int(time_signature.get("numerator", 4) or 4),
    )
    bar_grid_origin["section_source"] = section_selection["source"]
    bar_grid_origin["downbeat_engine"] = downbeat_consensus.get("selected_engine")
    bar_grid_origin["downbeat_engine_name"] = downbeat_consensus.get("selected_engine_name")
    downbeat_consensus["bar_grid_origin"] = bar_grid_origin
    time_signature["pre_consensus_meter"] = accent_time_signature
    time_signature["needs_review"] = bool(
        downbeat_consensus["needs_review"] or bar_grid_origin.get("status") != "ok"
    )
    time_signature["downbeat_consensus"] = downbeat_consensus
    time_signature["bar_grid_origin"] = bar_grid_origin
    selected_downbeat_validation = (
        (downbeat_results.get(str(downbeat_consensus.get("selected_engine"))) or {})
        .get("model_validation")
    )
    time_signature["model_validation"] = selected_downbeat_validation
    time_signature["validation_status"] = (
        "validated"
        if bool((selected_downbeat_validation or {}).get("meter_validated"))
        else "provisional"
    )
    beatgrid_summary["beat_needs_review"] = bool(
        beatgrid_summary.get("beat_needs_review")
        or downbeat_consensus["needs_review"]
        or bar_grid_origin.get("status") != "ok"
    )
    beat_details = dict(beatgrid_summary.get("beat_confidence_details") or {})
    beat_details["downbeat_consensus"] = downbeat_consensus
    beat_details["core_analysis_version"] = CORE_ANALYSIS_VERSION
    beatgrid_summary["beat_confidence_details"] = beat_details

    # Energy
    rms = librosa.feature.rms(y=y)[0]
    energy = float(np.clip(np.tanh(float(np.mean(rms)) * 8.0), 0.0, 1.0))
    energy_curve = _build_energy_curve(y, sr)
    loudness_profile = _analyze_loudness(y, sr)

    # Key detection. libKeyFinder is the primary DJ-facing route. Essentia and
    # madmom CNN independently verify it; the local CQT/CENS implementation is
    # invoked only when a primary route is unavailable or the routes conflict.
    key_routes: dict[str, dict] = {}
    key_errors: dict[str, str] = {}
    key_jobs: dict[Any, str] = {}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="key-family") as executor:
        if _env_flag("KEY_ENABLE_LIBKEYFINDER"):
            key_jobs[executor.submit(_analyze_key_libkeyfinder, file_path, y, sr)] = "libkeyfinder"
        if _env_flag("KEY_ENABLE_ESSENTIA"):
            key_jobs[executor.submit(
                _analyze_key_essentia, y, sr, max_duration=MAX_ANALYSIS_DURATION,
            )] = "essentia"
        if _env_flag("KEY_ENABLE_MADMOM"):
            key_jobs[executor.submit(_analyze_key_madmom, file_path)] = "madmom"

        for future in as_completed(key_jobs):
            route_name = key_jobs[future]
            try:
                key_routes[route_name] = future.result()
            except Exception as exc:
                key_errors[route_name] = f"{type(exc).__name__}: {exc}"

    route_keys = [result["camelot_key"] for result in key_routes.values()]
    needs_local_fallback = (
        not key_routes
        or "libkeyfinder" not in key_routes
        or (len(route_keys) >= 2 and len(set(route_keys)) == len(route_keys))
    )
    local_key_result: dict | None = None
    if needs_local_fallback:
        local_key_result = {
            **_analyze_key(y, sr),
            "engine": "librosa_chroma_fallback",
        }
    key_result = _choose_key_consensus(
        key_routes,
        errors=key_errors,
        local_fallback=local_key_result,
    )

    # SongFormer is authoritative for product-facing section boundaries and
    # labels.  All-In-One sections are retained only as an explicit fallback;
    # the two models are never blended.  Energy remains an attached attribute.
    section_route = section_selection.get("route") or {}
    cue_points = _functional_segments_to_cues(
        functional_segments,
        source=section_selection["segment_source"],
    )
    section_source = section_selection["source"]

    # Phrase map uses the same authoritative boundaries as cue_points. Bar counts
    # use the exported grid whose Bar 1 starts after the intro.
    phrase_map = _functional_segments_to_phrase_map(
        functional_segments,
        downbeats,
        source=section_selection["segment_source"],
    )
    phrase_map = _attach_phrase_energy(phrase_map, energy_curve)

    # ── Extended analysis ──────────────────────────────────────────
    # Section intensity scoring
    phrase_map = _score_section_intensity(phrase_map, energy_curve, y, sr)

    # Groove / danceability score
    groove = _compute_groove_score(beat_times, downbeats, bpm_curve, tempo_stability)

    # Transition windows (label/energy based, will be enhanced with stem data later)
    transition_windows = _build_transition_windows(phrase_map)
    spectral_centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    dancefloor_profile = _analyze_dancefloor_profile(
        bpm=bpm,
        energy=energy,
        groove=groove,
        spectral_centroid=spectral_centroid,
        phrase_map=phrase_map,
    )

    return {
        "core_analysis_version": CORE_ANALYSIS_VERSION,
        "bpm": round(bpm, 1),
        "duration": round(duration, 2),
        "energy": round(energy, 3),
        "key": key_result["key"],
        "camelot_key": key_result["camelot_key"],
        "key_confidence": key_result["key_confidence"],
        "key_profile": {
            "tonal_clarity": key_result["tonal_clarity"],
            "relative_ambiguity": key_result["relative_ambiguity"],
            "candidates": key_result["candidates"],
            "method": key_result["method"],
            "engine": key_result.get("engine"),
            "sample_rate": key_result.get("sample_rate"),
            "fallback_reason": key_result.get("fallback_reason"),
            "raw_key": key_result.get("raw_key"),
            "raw_scale": key_result.get("raw_scale"),
            "strength": key_result.get("strength"),
            "primary_engine": key_result.get("primary_engine"),
            "selected_engine": key_result.get("selected_engine"),
            "decision": key_result.get("decision"),
            "confidence_level": key_result.get("confidence_level"),
            "needs_review": key_result.get("needs_review"),
            "validation_status": key_result.get("validation_status"),
            "model_validation": key_result.get("model_validation"),
            "model_confidence": key_result.get("model_confidence"),
            "route_results": key_result.get("route_results", {}),
            "local_fallback": key_result.get("local_fallback"),
            "errors": key_result.get("errors", {}),
        },
        "beat_points": beat_points,
        "bpm_curve": bpm_curve,
        "tempo_stability": tempo_stability,
        **beatgrid_summary,
        "downbeats": downbeats,
        "cue_points": cue_points,
        "section_analysis": {
            "source": section_source,
            "authoritative_model": "songformer",
            "authoritative_boundary_model": "songformer",
            "structure_label_source": (
                "all_in_one_fallback_candidate"
                if section_selection["fallback_used"]
                else "songformer_candidate"
            ),
            "label_contract_version": LABEL_CONTRACT_VERSION,
            "intro_end_candidate": intro_end_candidate,
            "intro_end_candidate_details": intro_end_details,
            "semantic_intro_applied_to_bar_grid": False,
            "status": section_selection["status"],
            "engine": section_selection.get("engine"),
            "input_mode": section_route.get("input_mode"),
            "source_sample_rate": section_route.get("sample_rate"),
            "ffmpeg_shared_libraries_preloaded": bool(
                section_route.get("ffmpeg_shared_lib_dir")
            ),
            "functional_segments": functional_segments,
            "fallback_used": section_selection["fallback_used"],
            "fallback_policy": section_selection["fallback_policy"],
            "error": section_selection.get("songformer_error"),
            "songformer": {
                "engine": (songformer_route or {}).get("engine"),
                "model": (songformer_route or {}).get("model"),
                "pipeline": (songformer_route or {}).get("pipeline"),
                "device": (songformer_route or {}).get("device"),
                "frame_rate": (songformer_route or {}).get("frame_rate"),
                "runner_version": (songformer_route or {}).get("runner_version"),
                "label_contract_version": (songformer_route or {}).get(
                    "label_contract_version"
                ),
                "runtime_fingerprint": (songformer_route or {}).get(
                    "runtime_fingerprint"
                ),
                "cache_namespace": (songformer_route or {}).get("cache_namespace"),
            },
            "runtime_fingerprint": (songformer_route or {}).get(
                "runtime_fingerprint"
            ),
            "cache_namespace": (songformer_route or {}).get("cache_namespace"),
            "all_in_one_retained_for_rhythm": "all_in_one" in rhythm_results,
            "all_in_one_section_count_for_audit": section_selection[
                "all_in_one_segment_count_for_audit"
            ],
            "semantic_labels_from_energy": False,
            "bar_grid_origin": bar_grid_origin,
        },
        "phrase_map": phrase_map,
        "energy_curve": energy_curve,
        "loudness_profile": loudness_profile,
        "transition_windows": transition_windows,
        "time_signature": time_signature,
        "groove": groove,
        "danceability_score": dancefloor_profile["danceability_score"],
        "dancefloor_profile": dancefloor_profile,
        "dj_hot_cues": _generate_dj_hot_cues(phrase_map, transition_windows, energy_curve, duration),
        "transition_recommendations": _recommend_transition_techniques(
            phrase_map, transition_windows,
        ),
    }
