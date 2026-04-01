from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.responses import APIResponse
from app.modules.recommendations.schemas import RecommendationData, RecommendationRequest
from app.modules.recommendations.service import recommend_songs

router = APIRouter()


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
