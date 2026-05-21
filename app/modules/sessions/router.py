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


# --- RK3588 SessionEvent ingest (cypher protocol P7) ---

import os
from fastapi import Header, HTTPException
from app.modules.sessions.schemas import (
    RKEventBatchRequest,
    RKEventIngestData,
    RKEventListData,
    RKEventListItem,
)
from app.modules.sessions.service import (
    ingest_rk_events,
    list_rk_events,
)


def _check_rk_token(token: str | None) -> None:
    expected = os.getenv("HARBEAT_RK_TOKEN")
    if expected and token != expected:
        raise HTTPException(status_code=401, detail="invalid X-RK-Token")


@router.post("/rk/{session_id}/events", response_model=APIResponse[RKEventIngestData])
def ingest_rk_events_endpoint(
    session_id: str,
    payload: RKEventBatchRequest,
    db: Session = Depends(get_db),
    x_rk_token: str | None = Header(default=None),
):
    """RK3588 batch upload of session events. Recommended: flush every 5s or 50 events."""
    _check_rk_token(x_rk_token)
    n = ingest_rk_events(db, session_id, payload.rk_id, payload.events)
    return APIResponse(data=RKEventIngestData(accepted=n, session_id=session_id))


@router.get("/rk/{session_id}/events", response_model=APIResponse[RKEventListData])
def list_rk_events_endpoint(
    session_id: str,
    type: str | None = None,
    limit: int = 500,
    db: Session = Depends(get_db),
    x_rk_token: str | None = Header(default=None),
):
    _check_rk_token(x_rk_token)
    rows = list_rk_events(db, session_id, type_=type, limit=min(max(limit, 1), 5000))
    return APIResponse(data=RKEventListData(
        session_id=session_id,
        events=[
            RKEventListItem(ts=r.ts, rk_id=r.rk_id, type=r.type, data=r.data, received_at=r.received_at)
            for r in rows
        ],
    ))
