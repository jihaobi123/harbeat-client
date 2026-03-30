from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.interaction_log import UserInteractionLog
from app.schemas import (
    CypherRecommendationResponse,
    GeneratePracticeListRequest,
    GeneratePracticeListResponse,
    PracticeTrackItem,
)
from app.services import generate_practice_list, recommend_cypher_track

router = APIRouter(tags=["playlist"])


class InteractionCreate(BaseModel):
    user_id: int
    track_id: int
    action_type: str
    listen_mode: str
    current_dance_style: str
    play_duration_sec: float = 0.0
    completion_rate: float = 0.0
    skip_timestamp: float | None = None
    drum_boost_enabled: bool = False
    bpm_adjusted_to: float | None = None
    ab_loop_used: bool = False
    cue_points_added: int = 0
    rewind_count: int = 0


@router.post("/log-interaction")
def log_interaction(payload: InteractionCreate, db: Session = Depends(get_db)):
    row = UserInteractionLog(
        user_id=payload.user_id,
        track_id=payload.track_id,
        action_type=payload.action_type,
        listen_mode=payload.listen_mode,
        current_dance_style=payload.current_dance_style,
        play_duration_sec=payload.play_duration_sec,
        completion_rate=payload.completion_rate,
        skip_timestamp=payload.skip_timestamp,
        drum_boost_enabled=payload.drum_boost_enabled,
        bpm_adjusted_to=payload.bpm_adjusted_to,
        ab_loop_used=payload.ab_loop_used,
        cue_points_added=payload.cue_points_added,
        rewind_count=payload.rewind_count,
    )
    db.add(row)
    db.commit()
    return {"status": "success"}


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
