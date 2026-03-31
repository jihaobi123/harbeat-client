from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.responses import APIResponse
from app.modules.sessions.schemas import (
    InteractionLogRequest,
    PracticeListData,
    PracticeListRequest,
    SessionEndRequest,
    SessionEventRequest,
    SessionStartData,
    SessionStartRequest,
    SuccessData,
)
from app.modules.sessions.service import (
    create_session_event,
    end_session,
    generate_practice_list,
    log_interaction,
    start_session,
)

router = APIRouter()


@router.post("/start", response_model=APIResponse[SessionStartData])
def start_session_endpoint(payload: SessionStartRequest, db: Session = Depends(get_db)):
    session = start_session(db, user_id=payload.user_id, mode=payload.mode)
    return APIResponse(data=SessionStartData(session_id=session.id))


@router.post("/event", response_model=APIResponse[SuccessData])
def create_session_event_endpoint(payload: SessionEventRequest, db: Session = Depends(get_db)):
    create_session_event(
        db,
        session_id=payload.session_id,
        event_type=payload.event_type,
        event_value=payload.event_value,
        timestamp=payload.timestamp,
    )
    return APIResponse(data=SuccessData())


@router.post("/end", response_model=APIResponse[SuccessData])
def end_session_endpoint(payload: SessionEndRequest, db: Session = Depends(get_db)):
    end_session(db, payload.session_id)
    return APIResponse(data=SuccessData())


@router.post("/log-interaction", response_model=APIResponse[SuccessData])
def log_interaction_endpoint(payload: InteractionLogRequest, db: Session = Depends(get_db)):
    log_interaction(db, payload)
    return APIResponse(data=SuccessData())


@router.post("/generate-practice-list", response_model=APIResponse[PracticeListData])
def generate_practice_list_endpoint(payload: PracticeListRequest, db: Session = Depends(get_db)):
    tracks = generate_practice_list(
        db,
        user_id=payload.user_id,
        target_duration=payload.target_duration,
        dance_style=payload.dance_style,
    )
    return APIResponse(
        data=PracticeListData(
            user_id=payload.user_id,
            target_duration=payload.target_duration,
            tracks=tracks,
        )
    )
