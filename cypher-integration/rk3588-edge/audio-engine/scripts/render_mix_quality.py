#!/usr/bin/env python3
"""Offline render + metrics for HarBeat automix preset tuning.

This intentionally mirrors the RK engine's gain envelopes closely enough for
quality comparison, while staying dependency-light for Mac/RK debugging.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import AudioEngineMVP, STEM_AWARE_STYLES  # noqa: E402

SR = 44100
STEMS = ("vocals", "drums", "bass", "other")
STEM_PRESETS = (
    "vocal_handoff",
    "bass_swap",
    "drum_swap",
    "vocal_ducking",
    "instrumental_only",
    "vocal_solo_intro",
)
NON_STEM_PRESETS = ("blend", "filter", "echo_freeze", "rise", "melt", "cut", "slam")


def _entry_path(entry: object, cache_dir: Path | None = None) -> Path | None:
    if isinstance(entry, str):
        value = entry
        fmt = ""
    elif isinstance(entry, dict):
        value = next((str(entry.get(key)) for key in ("local_path", "path", "file", "url") if entry.get(key)), "")
        fmt = str(entry.get("format") or "")
    else:
        return None

    if value.startswith(("http://", "https://")):
        if cache_dir is None:
            return None
        cache_dir.mkdir(parents=True, exist_ok=True)
        suffix = f".{fmt.lstrip('.')}" if fmt else Path(value.split("?", 1)[0]).suffix or ".audio"
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:18]
        cached = cache_dir / f"{digest}{suffix}"
        if not cached.exists():
            try:
                urllib.request.urlretrieve(value, cached)
            except Exception:
                return None
        return cached

    path = Path(value)
    return path if path.exists() else None


def _read_wav(path: Path) -> np.ndarray:
    data, sr = sf.read(path, always_2d=True, dtype="float32")
    if sr != SR:
        raise ValueError(f"{path} sample rate {sr}, expected {SR}")
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    return data[:, :2]


def _segment(data: np.ndarray, start_sec: float, dur_sec: float) -> np.ndarray:
    start = max(0, int(round(start_sec * SR)))
    length = max(1, int(round(dur_sec * SR)))
    end = min(len(data), start + length)
    out = np.zeros((length, 2), dtype=np.float32)
    if start < len(data):
        out[: end - start] = data[start:end]
    return out


def _silent_segment(dur_sec: float) -> np.ndarray:
    return np.zeros((max(1, int(round(dur_sec * SR))), 2), dtype=np.float32)


def _track_files(report: dict) -> dict[str, dict]:
    tracks = report.get("tracks") or report.get("mix_plan", {}).get("tracks") or []
    out = {}
    for idx, track in enumerate(tracks):
        if not isinstance(track, dict):
            continue
        sid = str(track.get("song_id", track.get("id", f"track_{idx}")))
        out[sid] = track.get("files") or {}
    return out


def _load_track_audio(
    files: dict,
    start_sec: float,
    dur_sec: float,
    *,
    require_stems: bool,
    cache_dir: Path | None = None,
) -> dict[str, np.ndarray] | None:
    if require_stems:
        stems = files.get("stems") if isinstance(files, dict) else None
        stem_paths = {stem: _entry_path(stems.get(stem), cache_dir) for stem in STEMS} if isinstance(stems, dict) else {}
        if stem_paths and all(stem_paths.get(stem) for stem in STEMS):
            return {stem: _segment(_read_wav(stem_paths[stem]), start_sec, dur_sec) for stem in STEMS}  # type: ignore[arg-type]
        return None

    original = _entry_path(files.get("original"), cache_dir) if isinstance(files, dict) else None
    if not original:
        return None
    full = _segment(_read_wav(original), start_sec, dur_sec)
    silent = _silent_segment(dur_sec)
    return {
        "vocals": full,
        "drums": silent.copy(),
        "bass": silent.copy(),
        "other": silent.copy(),
    }


def _rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))


def _db(x: float) -> float:
    return round(20.0 * math.log10(max(x, 1e-9)), 3)


def _one_pole_filter(audio: np.ndarray, cutoff_hz: float, *, highpass: bool) -> np.ndarray:
    cutoff_hz = max(20.0, min(float(cutoff_hz), SR * 0.45))
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / SR
    alpha = rc / (rc + dt) if highpass else dt / (rc + dt)
    out = np.zeros_like(audio)
    if highpass:
        prev_y = np.zeros(2, dtype=np.float32)
        prev_x = audio[0].copy()
        for i, x in enumerate(audio):
            y = alpha * (prev_y + x - prev_x)
            out[i] = y
            prev_y = y
            prev_x = x
    else:
        y = np.zeros(2, dtype=np.float32)
        for i, x in enumerate(audio):
            y = y + alpha * (x - y)
            out[i] = y
    return out


def _filter_blocks(audio: np.ndarray, start_hz: float, end_hz: float, *, highpass: bool) -> np.ndarray:
    out = np.zeros_like(audio)
    block = int(SR * 0.1)
    total = max(1, len(audio))
    for start in range(0, len(audio), block):
        end = min(len(audio), start + block)
        x = (start + end) * 0.5 / total
        cutoff = start_hz * ((end_hz / start_hz) ** x)
        out[start:end] = _one_pole_filter(audio[start:end], cutoff, highpass=highpass)
    return out


def _echo(audio: np.ndarray, feedback: float = 0.35, wet: float = 0.45, delay_sec: float = 0.25) -> np.ndarray:
    delay = int(delay_sec * SR)
    out = audio.copy()
    for i in range(delay, len(out)):
        out[i] += out[i - delay] * feedback * wet
    return out


def _render_style(style: str, a_stems: dict[str, np.ndarray], b_stems: dict[str, np.ndarray]) -> tuple[np.ndarray, dict]:
    n = min(len(next(iter(a_stems.values()))), len(next(iter(b_stems.values()))))
    mix = np.zeros((n, 2), dtype=np.float32)
    vocal_overlap = 0.0
    bass_overlap = 0.0

    for start in range(0, n, 1024):
        end = min(n, start + 1024)
        x = start / max(1, n - 1)
        a_g, b_g = AudioEngineMVP._style_envelopes(style, x)
        if style in STEM_AWARE_STYLES:
            for stem in STEMS:
                mix[start:end] += a_stems[stem][start:end] * float(a_g.get(stem, 0.0))
                mix[start:end] += b_stems[stem][start:end] * float(b_g.get(stem, 0.0))
            vocal_overlap += min(float(a_g.get("vocals", 0.0)), float(b_g.get("vocals", 0.0))) * (end - start)
            bass_overlap += min(float(a_g.get("bass", 0.0)), float(b_g.get("bass", 0.0))) * (end - start)
        else:
            a_full = sum(a_stems.values())
            b_full = sum(b_stems.values())
            mix[start:end] += a_full[start:end] * float(a_g.get("full", 0.0))
            mix[start:end] += b_full[start:end] * float(b_g.get("full", 0.0))

    if style == "filter":
        midpoint = n // 2
        mix[:midpoint] = _filter_blocks(mix[:midpoint], 18000.0, 350.0, highpass=False)
        mix[midpoint:] = _filter_blocks(mix[midpoint:], 250.0, 18000.0, highpass=False)
    elif style == "echo_freeze":
        mix = _echo(mix, feedback=0.42, wet=0.55)
        mix = _filter_blocks(mix, 900.0, 40.0, highpass=True)
    elif style == "rise":
        mix = _filter_blocks(mix, 1200.0, 35.0, highpass=True)
    elif style == "melt":
        mix = _echo(mix, feedback=0.28, wet=0.35)
        mix = _filter_blocks(mix, 1200.0, 18000.0, highpass=False)
    elif style in ("vocal_handoff", "vocal_solo_intro"):
        mix = _filter_blocks(mix, 800.0, 30.0, highpass=True)

    peak = float(np.max(np.abs(mix)))
    if peak > 0.98:
        mix = mix / (peak / 0.98)
    return mix, {
        "vocal_overlap": round(vocal_overlap / max(1, n), 4),
        "bass_overlap": round(bass_overlap / max(1, n), 4),
    }


def _metrics(style: str, audio: np.ndarray, extra: dict) -> dict:
    thirds = np.array_split(audio, 3)
    peak = float(np.max(np.abs(audio)))
    rms = _rms(audio)
    third_rms = [_rms(chunk) for chunk in thirds]
    energy_slope = third_rms[-1] - third_rms[0]
    silence = float(np.mean(np.sqrt(np.mean(np.square(audio), axis=1)) < 1e-4))
    score = (
        1.0
        - min(0.35, max(0.0, peak - 0.98) * 2.0)
        - min(0.25, silence * 2.5)
        - min(0.20, extra.get("vocal_overlap", 0.0) * 0.8)
        - min(0.15, extra.get("bass_overlap", 0.0) * 0.5)
        + min(0.10, max(0.0, energy_slope) * 1.5)
    )
    return {
        "style": style,
        "peak": round(peak, 5),
        "rms_db": _db(rms),
        "third_rms_db": [_db(x) for x in third_rms],
        "silence_ratio": round(silence, 5),
        "energy_slope": round(float(energy_slope), 5),
        "quality_score": round(max(0.0, min(1.0, score)), 4),
        **extra,
    }


def render_batch_report(
    batch_report: Path,
    out_dir: Path,
    *,
    limit: int | None = None,
    cache_dir: Path | None = None,
) -> list[dict]:
    """Render selected transitions from a batch report.

    The report shape is intentionally simple:
      tracks[].files.original.path/local_path and tracks[].files.stems.<stem>.path
      mix_plan.transitions[] with from_song/to_song/style/fallback_style/timing.
    """
    report = json.loads(Path(batch_report).read_text(encoding="utf-8"))
    files_by_song = _track_files(report)
    transitions = report.get("mix_plan", {}).get("transitions") or report.get("transitions") or []
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[dict] = []

    for idx, tr in enumerate(transitions[:limit] if limit else transitions):
        from_song = str(tr.get("from_song", tr.get("from_song_id")))
        to_song = str(tr.get("to_song", tr.get("to_song_id")))
        fade_sec = float(tr.get("fade_sec", tr.get("crossfade_sec", 8.0)) or 8.0)
        a_start = float(tr.get("from_at_sec", tr.get("from_out_sec", 0.0)) or 0.0)
        b_start = float(tr.get("to_at_sec", tr.get("to_in_sec", 0.0)) or 0.0)
        styles = []
        for style in (tr.get("style"), tr.get("fallback_style")):
            if style and style not in styles:
                styles.append(str(style))

        for style in styles:
            require_stems = style in STEM_AWARE_STYLES
            a_audio = _load_track_audio(
                files_by_song.get(from_song, {}),
                a_start,
                fade_sec,
                require_stems=require_stems,
                cache_dir=cache_dir,
            )
            b_audio = _load_track_audio(
                files_by_song.get(to_song, {}),
                b_start,
                fade_sec,
                require_stems=require_stems,
                cache_dir=cache_dir,
            )
            if not a_audio or not b_audio:
                rendered.append({
                    "transition_index": idx,
                    "from_song": from_song,
                    "to_song": to_song,
                    "style": style,
                    "verdict": "skipped_missing_audio",
                })
                continue
            audio, extra = _render_style(style, a_audio, b_audio)
            path = out_dir / f"{idx:02d}_{from_song}_to_{to_song}_{style}.wav"
            sf.write(path, audio, SR)
            metrics = _metrics(style, audio, extra)
            rendered.append({
                "transition_index": idx,
                "from_song": from_song,
                "to_song": to_song,
                "style": style,
                "tier": "stem_aware" if style in STEM_AWARE_STYLES else "non_stem",
                "path": str(path),
                "metrics": metrics,
                "verdict": "ok" if metrics["peak"] <= 0.98 and metrics["silence_ratio"] < 0.2 else "review",
            })

    render_report = out_dir / "batch_render_report.json"
    render_report.write_text(json.dumps({"source_report": str(batch_report), "renders": rendered}, indent=2) + "\n", encoding="utf-8")
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a-dir", type=Path, default=Path("/tmp/stems/A"))
    parser.add_argument("--b-dir", type=Path, default=Path("/tmp/stems/B"))
    parser.add_argument("--a-start", type=float, default=144.615)
    parser.add_argument("--b-start", type=float, default=32.16)
    parser.add_argument("--duration", type=float, default=20.645)
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/harbeat_mix_quality_renders"))
    parser.add_argument("--batch-report", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/harbeat_mix_quality_cache"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.batch_report:
        rendered = render_batch_report(args.batch_report, args.out_dir, limit=args.limit, cache_dir=args.cache_dir)
        print(json.dumps({"renders": len(rendered), "report": str(args.out_dir / "batch_render_report.json")}, indent=2))
        return

    a_raw = {stem: _segment(_read_wav(args.a_dir / f"{stem}.wav"), args.a_start, args.duration) for stem in STEMS}
    b_raw = {stem: _segment(_read_wav(args.b_dir / f"{stem}.wav"), args.b_start, args.duration) for stem in STEMS}

    results = []
    for style in (*STEM_PRESETS, *NON_STEM_PRESETS):
        audio, extra = _render_style(style, a_raw, b_raw)
        out_path = args.out_dir / f"{style}.wav"
        sf.write(out_path, audio, SR)
        item = _metrics(style, audio, extra)
        item["path"] = str(out_path)
        item["tier"] = "stem_aware" if style in STEM_PRESETS else "non_stem"
        results.append(item)

    results.sort(key=lambda x: x["quality_score"], reverse=True)
    best = results[0]
    report = {
        "pair": "Nice For What -> Popular",
        "a_start": args.a_start,
        "b_start": args.b_start,
        "duration": args.duration,
        "best_style": best["style"],
        "best_path": best["path"],
        "results": results,
    }
    report_path = args.out_dir / "quality_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"best_style": best["style"], "best_path": best["path"], "report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
