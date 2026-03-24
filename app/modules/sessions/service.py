from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.sessions.models import Session as PlaySession
from app.modules.sessions.models import SessionEvent
from app.modules.users.service import get_user_or_404


def start_session(db: Session, user_id: int, mode: str) -> PlaySession:
    get_user_or_404(db, user_id)
    session = PlaySession(user_id=user_id, mode=mode)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def create_session_event(
    db: Session,
    session_id: int,
    event_type: str,
    event_value: Optional[str],
    timestamp: datetime,
) -> SessionEvent:
    session = db.query(PlaySession).filter(PlaySession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    event = SessionEvent(
        session_id=session_id,
        event_type=event_type,
        event_value=event_value or f"timestamp={timestamp.isoformat()}",
        created_at=timestamp,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def end_session(db: Session, session_id: int) -> PlaySession:
    session = db.query(PlaySession).filter(PlaySession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    session.end_time = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session
