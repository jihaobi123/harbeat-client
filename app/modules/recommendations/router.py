from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.responses import APIResponse
from app.modules.recommendations.schemas import (
    AddToLibraryData,
    AddToLibraryRequest,
    DiscoverData,
    DiscoverRequest,
    ImportFromVibeRequest,
    RecommendationData,
    RecommendationRequest,
    VibeSearchData,
    VibeSearchRequest,
)
from app.modules.recommendations.service import (
    add_song_to_library,
    discover_songs,
    import_from_vibe,
    recommend_songs,
    vibe_search,
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


# ─────────────────────── Vibe Search (CLAP + Spotify hybrid) ────────────────── #


@router.post("/vibe-search", response_model=APIResponse[VibeSearchData])
def vibe_search_endpoint(
    payload: VibeSearchRequest,
    db: Session = Depends(get_db),
):
    """Free-form text → CLAP local search + Spotify candidates merged."""
    data = vibe_search(
        db,
        query=payload.query,
        user_id=payload.user_id,
        top_k=payload.top_k,
    )
    return APIResponse(data=data)


@router.post("/import-from-vibe")
def import_from_vibe_endpoint(
    payload: ImportFromVibeRequest,
    db: Session = Depends(get_db),
):
    """Vibe → Spotify → CLAP rerank → download + index."""
    data = import_from_vibe(
        db,
        user_id=payload.user_id,
        vibe_description=payload.vibe_description,
        top_k=payload.top_k,
        auto_import=payload.auto_import,
    )
    return APIResponse(data=data)
