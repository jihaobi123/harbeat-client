from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import RecommendRequest, RecommendResponse
from app.services import get_simple_recommendations

router = APIRouter(prefix="/recommend", tags=["recommend"])


@router.post("", response_model=RecommendResponse)
def recommend(payload: RecommendRequest, db: Session = Depends(get_db)):
    items = get_simple_recommendations(db, payload.top_k)
    return RecommendResponse(user_id=payload.user_id, items=items)
