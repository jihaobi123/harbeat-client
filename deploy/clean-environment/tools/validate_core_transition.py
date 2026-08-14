#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine, text

from harbeat_transition_planner import plan_fast_cut_transition
from harbeat_transition_renderer import (
    DefaultRenderError,
    FAST_CUT_RENDERER_VERSION,
    ensure_reference_render,
)


FEATURE_SOURCE = "dj_structure_precomputed_window_v2"


def resolve_asset_path(stored_path: object, asset_root: Path) -> Path:
    raw = str(stored_path or "").replace("\\", "/")
    marker = "/music-files/"
    relative = raw.split(marker, 1)[1] if marker in raw else Path(raw).name
    path = asset_root / relative
    if not path.is_file():
        raise FileNotFoundError(f"asset is missing below configured root: {relative}")
    return path


def load_song(engine: Any, song_id: str, asset_root: Path) -> SimpleNamespace:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT * FROM public.library_songs WHERE id = :song_id"),
            {"song_id": song_id},
        ).mappings().first()
    if row is None:
        raise ValueError(f"library song not found: {song_id}")
    payload = dict(row)
    payload["source_path"] = str(resolve_asset_path(payload.get("source_path"), asset_root))
    return SimpleNamespace(**payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_plan(plan: dict[str, Any]) -> str:
    return json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def assert_plan_contract(plan: dict[str, Any]) -> None:
    default = plan.get("default_mix") or {}
    if default.get("audio_feature_source") != FEATURE_SOURCE:
        raise AssertionError("planner did not use dj_structure_v2")
    if default.get("required_renderer_version") != FAST_CUT_RENDERER_VERSION:
        raise AssertionError("planner did not require v7 renderer")
    if any(
        bool(value)
        for value in (
            plan.get("fallback_used"),
            plan.get("degraded"),
            default.get("fallback_used"),
            default.get("degraded"),
        )
    ):
        raise AssertionError("planner returned fallback or degraded output")


def validate(args: argparse.Namespace) -> dict[str, Any]:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing")
    asset_root = args.asset_root.resolve(strict=True)
    state_root = args.state_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, pool_pre_ping=True)
    previous = load_song(engine, args.from_song_id, asset_root)
    next_song = load_song(engine, args.to_song_id, asset_root)

    plan_started = time.perf_counter()
    plans = [
        plan_fast_cut_transition(
            previous,
            next_song,
            cursor_sec=args.cursor_sec,
            min_exit_sec=args.min_exit_sec,
            max_exit_sec=args.max_exit_sec,
            fade_sec=args.fade_sec,
            require_precomputed_v2=True,
        )
        for _ in range(args.plan_runs)
    ]
    plan_elapsed = time.perf_counter() - plan_started
    for plan in plans:
        assert_plan_contract(plan)
    plan_hashes = {hashlib.sha256(canonical_plan(plan).encode("utf-8")).hexdigest() for plan in plans}
    if len(plan_hashes) != 1:
        raise AssertionError("planner output is not deterministic")
    plan = plans[0]
    plan_path = state_root / "transition-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    renders: list[dict[str, Any]] = []
    for index in range(args.render_runs):
        cache_root = state_root / f"render-{index + 1}"
        os.environ["HARBEAT_DEFAULT_MIX_PAIR_CACHE_DIR"] = str(cache_root)
        started = time.perf_counter()
        meta = ensure_reference_render(previous, next_song, plan)
        elapsed = time.perf_counter() - started
        wav_path = Path(meta["transition_render_path"])
        meta_path = Path(meta["transition_render_meta_path"])
        if meta.get("renderer_version") != FAST_CUT_RENDERER_VERSION:
            raise AssertionError("renderer did not produce required v7 output")
        if meta.get("audio_feature_source") != FEATURE_SOURCE:
            raise AssertionError("renderer metadata lost v2 feature source")
        import soundfile as sf

        info = sf.info(wav_path)
        if info.frames <= 0 or info.samplerate <= 0:
            raise AssertionError("rendered WAV is not decodable")
        renders.append(
            {
                "run": index + 1,
                "elapsed_sec": round(elapsed, 3),
                "wav_sha256": sha256_file(wav_path),
                "meta_sha256": sha256_file(meta_path),
                "frames": info.frames,
                "sample_rate": info.samplerate,
                "from_at_sec": meta.get("from_at_sec"),
                "to_at_sec": meta.get("to_at_sec"),
                "resume_at_sec": meta.get("resume_at_sec"),
                "renderer_version": meta.get("renderer_version"),
                "audio_feature_source": meta.get("audio_feature_source"),
            }
        )

    typed_failures: dict[str, str] = {}
    previous_without_v2 = copy.copy(previous)
    previous_without_v2.music_features = {}
    try:
        plan_fast_cut_transition(
            previous_without_v2,
            next_song,
            cursor_sec=args.cursor_sec,
            min_exit_sec=args.min_exit_sec,
            max_exit_sec=args.max_exit_sec,
            require_precomputed_v2=True,
        )
    except ValueError as exc:
        typed_failures["missing_v2"] = type(exc).__name__
    else:
        raise AssertionError("missing v2 data did not fail")

    bad_renderer_plan = copy.deepcopy(plan)
    bad_renderer_plan["default_mix"]["required_renderer_version"] = "unsupported-renderer"
    os.environ["HARBEAT_DEFAULT_MIX_PAIR_CACHE_DIR"] = str(state_root / "negative-renderer")
    try:
        ensure_reference_render(previous, next_song, bad_renderer_plan)
    except DefaultRenderError as exc:
        typed_failures["unsupported_renderer"] = type(exc).__name__
    else:
        raise AssertionError("unsupported renderer did not fail")

    missing_audio = copy.copy(previous)
    missing_audio.source_path = str(state_root / "absent.wav")
    missing_audio_plan = copy.deepcopy(plan)
    missing_audio_plan["pair_id"] = f"{plan['pair_id']}-missing-audio"
    missing_audio_plan["default_mix"]["pair_id"] = missing_audio_plan["pair_id"]
    os.environ["HARBEAT_DEFAULT_MIX_PAIR_CACHE_DIR"] = str(state_root / "negative-audio")
    try:
        ensure_reference_render(missing_audio, next_song, missing_audio_plan)
    except DefaultRenderError as exc:
        typed_failures["missing_audio"] = type(exc).__name__
    else:
        raise AssertionError("missing audio did not fail")

    return {
        "schema_version": 1,
        "passed": True,
        "from_song_id": args.from_song_id,
        "to_song_id": args.to_song_id,
        "plan_runs": args.plan_runs,
        "plan_deterministic": True,
        "plan_sha256": next(iter(plan_hashes)),
        "plan_artifact_sha256": sha256_file(plan_path),
        "plan_total_elapsed_sec": round(plan_elapsed, 3),
        "audio_feature_source": FEATURE_SOURCE,
        "renderer_version": FAST_CUT_RENDERER_VERSION,
        "fallback": False,
        "degraded": False,
        "render_runs": renders,
        "render_output_deterministic": len({row["wav_sha256"] for row in renders}) == 1,
        "typed_failures": typed_failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-song-id", required=True)
    parser.add_argument("--to-song-id", required=True)
    parser.add_argument("--asset-root", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cursor-sec", type=float, default=0.0)
    parser.add_argument("--min-exit-sec", type=float, default=10.0)
    parser.add_argument("--max-exit-sec", type=float, default=15.0)
    parser.add_argument("--fade-sec", type=float, default=6.5)
    parser.add_argument("--plan-runs", type=int, default=20)
    parser.add_argument("--render-runs", type=int, default=5)
    args = parser.parse_args()
    report = validate(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
