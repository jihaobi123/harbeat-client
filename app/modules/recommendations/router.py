from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.responses import APIResponse
from app.modules.recommendations.schemas import (
    AddToLibraryData,
    AddToLibraryRequest,
    DiscoverData,
    DiscoverRequest,
    RecommendationData,
    RecommendationRequest,
    ReindexClapData,
    ReindexData,
    VectorStoreStatsData,
    VibeSearchData,
    VibeSearchRequest,
)
from app.modules.recommendations.service import (
    add_song_to_library,
    discover_songs,
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


@router.post("/vibe-search", response_model=APIResponse[VibeSearchData])
def vibe_search_endpoint(
    payload: VibeSearchRequest,
    db: Session = Depends(get_db),
):
    data = vibe_search(db, query=payload.query, user_id=payload.user_id, top_k=payload.top_k)
    return APIResponse(data=data)


@router.post("/reindex", response_model=APIResponse[ReindexData])
def reindex_endpoint(db: Session = Depends(get_db)):
    """Rebuild the text-based ChromaDB index from all songs in the database."""
    from app.modules.recommendations.vector_store import index_all_songs_from_db
    count = index_all_songs_from_db()
    return APIResponse(data=ReindexData(indexed_count=count))


@router.post("/reindex-clap", response_model=APIResponse[ReindexClapData])
def reindex_clap_endpoint(db: Session = Depends(get_db)):
    """Regenerate CLAP audio embeddings for all songs (slow: ~30-60s/song)."""
    from app.modules.recommendations.vector_store import reindex_all_clap
    result = reindex_all_clap()
    return APIResponse(data=ReindexClapData(**result))


@router.get("/vector-stats", response_model=APIResponse[VectorStoreStatsData])
def vector_stats_endpoint():
    """Get ChromaDB vector store statistics (CLAP + text collections)."""
    from app.modules.recommendations.vector_store import get_collection_stats
    stats = get_collection_stats()
    return APIResponse(data=VectorStoreStatsData(**stats))
