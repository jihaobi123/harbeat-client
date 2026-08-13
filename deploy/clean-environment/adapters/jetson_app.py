from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, HTTPException

from .config import AdapterConfig, JETSON_SERVICES


def create_jetson_app(config: AdapterConfig) -> FastAPI:
    if config.service not in JETSON_SERVICES:
        raise ValueError(f"not a Jetson service: {config.service}")
    config.prepare_shadow_directories()
    app = FastAPI(title=f"HarBeat clean {config.service}", version="0.3.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": config.service,
            "profile": config.profile,
            "mode": config.mode,
            "release": "0.3.0",
            "production_ready": False,
        }

    if config.service == "catalog-api":
        _catalog_routes(app)
    elif config.service == "analysis-worker":
        _analysis_routes(app)
    elif config.service == "planning-api":
        _planning_routes(app)
    elif config.service == "render-worker":
        _render_routes(app, config)
    elif config.service == "stem-worker":
        _stem_routes(app, config)
    return app


def _catalog_routes(app: FastAPI) -> None:
    from harbeat_library_catalog.models import LibrarySong, Playlist
    from harbeat_library_catalog.service import CatalogService

    class RequestRepository:
        def __init__(self, songs: list[dict[str, Any]], playlist: dict[str, Any]) -> None:
            self.songs = [LibrarySong.from_api(row) for row in songs]
            self.playlist = Playlist.from_api(playlist)

        def list_library_songs(self) -> list[Any]:
            return list(self.songs)

        def get_playlist(self, playlist_id: int) -> Any:
            return self.playlist

    @app.post("/catalog/resolve-playlist")
    def resolve_playlist(body: dict[str, Any]) -> dict[str, Any]:
        try:
            repository = RequestRepository(list(body.get("songs") or []), dict(body.get("playlist") or {}))
            result = CatalogService(repository).resolve_playlist(int(body.get("playlist_id") or 0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "complete": result.complete,
            "songs": [dataclasses.asdict(row) for row in result.songs],
            "unresolved_catalog_song_ids": list(result.unresolved_catalog_song_ids),
        }


def _analysis_routes(app: FastAPI) -> None:
    from harbeat_audio_preprocess.service import PreprocessService

    class RequestRepository:
        def __init__(self, features: dict[str, Any]) -> None:
            self.features = dict(features)

        def load_features(self, song_id: str) -> dict[str, Any]:
            return dict(self.features)

        def save_features(self, song_id: str, features: dict[str, Any]) -> None:
            self.features = dict(features)

    @app.post("/analysis/process")
    def process(body: dict[str, Any]) -> dict[str, Any]:
        repository = RequestRepository(dict(body.get("features") or {}))
        payload = body.get("analysis_payload")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="analysis_payload is required")
        service = PreprocessService(repository, lambda _song_id: payload)
        try:
            result = service.process(str(body.get("song_id") or ""), force=bool(body.get("force", False)))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "song_id": result.song_id,
            "payload": dict(result.payload),
            "features": repository.features,
            "reused": result.reused,
        }


def _planning_routes(app: FastAPI) -> None:
    from harbeat_transition_planner import PlanningMode, PlanningRequest, TransitionPlanningService

    @app.post("/planning/transition")
    def plan(body: dict[str, Any]) -> dict[str, Any]:
        try:
            mode = PlanningMode(str(body.get("mode") or ""))
            previous = _song_namespace(body.get("previous_song"))
            next_song = _song_namespace(body.get("next_song"))
            options = body.get("options") or {}
            if not isinstance(options, dict):
                raise ValueError("options must be an object")
            return TransitionPlanningService().plan(PlanningRequest(mode, previous, next_song, options))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


def _render_routes(app: FastAPI, config: AdapterConfig) -> None:
    @app.post("/render/transition")
    def render(body: dict[str, Any]) -> dict[str, Any]:
        from harbeat_transition_renderer import DefaultRenderError, ensure_reference_render

        os.environ["HARBEAT_DEFAULT_MIX_PAIR_CACHE_DIR"] = str(config.state_root / "pairs")
        try:
            previous = _song_namespace(body.get("previous_song"))
            next_song = _song_namespace(body.get("next_song"))
            plan = body.get("plan")
            if not isinstance(plan, dict):
                raise ValueError("plan is required")
            return ensure_reference_render(previous, next_song, plan)
        except (DefaultRenderError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


def _stem_routes(app: FastAPI, config: AdapterConfig) -> None:
    @app.post("/stems/separate")
    def separate(body: dict[str, Any]) -> dict[str, Any]:
        from harbeat_stem_separation import StemSeparationError, StemSeparator, separation_result

        audio_path = _contained_path(config.asset_root, body.get("audio_path"), must_exist=True)
        output_root = _contained_path(config.state_root, body.get("output_root"), must_exist=False)
        separator = StemSeparator(
            model=str(body.get("model") or "htdemucs"),
            timeout_sec=int(body.get("timeout_sec") or 120),
        )
        try:
            stems = separator.separate(str(audio_path), str(output_root))
        except StemSeparationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return separation_result("separated", stems)


def _song_namespace(value: Any) -> SimpleNamespace:
    if not isinstance(value, dict):
        raise ValueError("song must be an object")
    row = dict(value)
    if "duration" not in row and "duration_sec" in row:
        row["duration"] = row["duration_sec"]
    return SimpleNamespace(**row)


def _contained_path(root: Path, value: Any, *, must_exist: bool) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="path is required")
    path = Path(raw).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="path is outside configured root") from exc
    if must_exist and not path.is_file():
        raise HTTPException(status_code=422, detail="input file does not exist")
    return path
