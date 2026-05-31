import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
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
logger = logging.getLogger(__name__)


class RkSessionEventsRequest(BaseModel):
    rk_id: str | None = None
    events: list[dict] = Field(default_factory=list)


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


@router.post("/rk/{session_id}/events", response_model=APIResponse[dict])
def ingest_rk_session_events_endpoint(session_id: str, payload: RkSessionEventsRequest):
    """Compatibility endpoint for RK edge-agent event flushes.

    RK session IDs are device-generated strings, while the legacy practice
    session table uses integer IDs. Accept the flush so edge-agent does not
    repeatedly retry and flood logs; structured persistence can be added when
    the cloud session schema is widened to string IDs.
    """
    logger.info(
        "[RK_SESSION_EVENTS] session_id=%s rk_id=%s count=%d",
        session_id,
        payload.rk_id,
        len(payload.events),
    )
    return APIResponse(data={"success": True, "accepted": len(payload.events)})


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
