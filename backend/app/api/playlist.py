from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    CypherRecommendationResponse,
    GeneratePracticeListRequest,
    GeneratePracticeListResponse,
    PracticeTrackItem,
)
from app.services import generate_practice_list, recommend_cypher_track

router = APIRouter(tags=["playlist"])


@router.post("/generate-practice-list", response_model=GeneratePracticeListResponse)
def generate_practice(payload: GeneratePracticeListRequest, db: Session = Depends(get_db)):
    tracks = generate_practice_list(db, payload.user_id, payload.target_duration)

    return GeneratePracticeListResponse(
        user_id=payload.user_id,
        target_duration=payload.target_duration,
        tracks=[
            PracticeTrackItem(
                id=t.id,
                title=t.title,
                bpm=t.bpm,
                camelot_key=t.camelot_key,
                energy=t.energy,
                genre_tags=t.genre_tags or {},
            )
            for t in tracks
        ],
    )


@router.get("/recommend-cypher", response_model=CypherRecommendationResponse)
def recommend_cypher(user_id: int, db: Session = Depends(get_db)):
    result = recommend_cypher_track(db, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="No cypher track found for this user")

    track, score = result
    return CypherRecommendationResponse(track_id=track.id, title=track.title, score=score)
