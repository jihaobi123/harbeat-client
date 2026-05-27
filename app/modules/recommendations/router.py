from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.responses import APIResponse
from app.modules.recommendations import vibe as vibe_search
from app.modules.recommendations.schemas import (
    AddToLibraryData,
    AddToLibraryRequest,
    DiscoverData,
    DiscoverRequest,
    RecommendationData,
    RecommendationRequest,
)
from app.modules.recommendations.service import (
    add_song_to_library,
    discover_songs,
    recommend_songs,
)

router = APIRouter()


@router.post("/discover", response_model=APIResponse[DiscoverData])
def discover_endpoint(
    payload: DiscoverRequest,
    db: Session = Depends(get_db),
):
    data = discover_songs(db, user_id=payload.user_id)
    return APIResponse(data=data)


@router.post("/add-to-library", response_model=APIResponse[AddToLibraryData])
def add_to_library_endpoint(
    payload: AddToLibraryRequest,
    db: Session = Depends(get_db),
):
    data = add_song_to_library(db, user_id=payload.user_id, song_id=payload.song_id)
    return APIResponse(data=data)


@router.post("/for-user", response_model=APIResponse[RecommendationData])
def get_recommendations_endpoint(
    payload: RecommendationRequest,
    db: Session = Depends(get_db),
):
    songs = recommend_songs(
        db,
        user_id=payload.user_id,
        mode=payload.mode,
        current_song_id=payload.current_song_id,
        target_energy=payload.target_energy,
        source=payload.source,
    )
    return APIResponse(data=RecommendationData(songs=songs))


# ───────────────────────── Vibe Search (Spotify-style) ─────────────────────── #

class VibeSearchRequest(BaseModel):
    query: str
    user_id: int | None = None
    top_k: int = 12


class ImportFromVibeRequest(BaseModel):
    user_id: int
    vibe_description: str
    top_k: int = 5
    auto_import: bool = True


@router.post("/vibe-search")
def vibe_search_endpoint(
    payload: VibeSearchRequest,
    db: Session = Depends(get_db),
):
    """Free-form text → ranked catalog songs (Spotify-style audio features)."""
    data = vibe_search.search(
        db, user_id=payload.user_id, query=payload.query, top_k=payload.top_k,
    )
    return APIResponse(data=data)


@router.post("/import-from-vibe")
def import_from_vibe_endpoint(
    payload: ImportFromVibeRequest,
    db: Session = Depends(get_db),
):
    """Vibe-search then auto-add the top results to the user's library."""
    result = vibe_search.search(
        db, user_id=payload.user_id, query=payload.vibe_description, top_k=payload.top_k,
    )
    imported: list[dict] = []
    failed: list[dict] = []
    if payload.auto_import:
        for s in result["songs"]:
            sid = s.get("song_id")
            if not sid or s.get("in_library"):
                continue
            try:
                lib = add_song_to_library(db, user_id=payload.user_id, song_id=int(sid))
                imported.append({
                    "song_id": sid,
                    "library_song_id": lib.library_song_id,
                    "title": lib.title,
                    "artist": lib.artist,
                })
            except Exception as exc:  # noqa: BLE001 — surface error per item
                failed.append({"song_id": sid, "title": s.get("title"), "error": str(exc)})
    return APIResponse(data={
        "query": result["query"],
        "vibe_description": result["vibe_description"],
        "genres": result["genres"],
        "candidates": result["songs"],
        "imported": imported,
        "failed": failed,
    })
