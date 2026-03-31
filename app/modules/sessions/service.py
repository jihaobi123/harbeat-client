from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.sessions.models import Session as PlaySession
from app.modules.sessions.models import SessionEvent, UserInteractionLog
from app.modules.sessions.schemas import InteractionLogRequest, PracticeTrackItem
from app.modules.sessions.playlist_engine import build_practice_list
from app.modules.library.models import LibrarySong
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


def log_interaction(db: Session, payload: InteractionLogRequest) -> UserInteractionLog:
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
    return row


def generate_practice_list(
    db: Session,
    user_id: int,
    target_duration: int,
    dance_style: Optional[str] = None,
) -> list[PracticeTrackItem]:
    query = db.query(LibrarySong).filter(LibrarySong.user_id == user_id)
    if dance_style:
        # 如果指定舞种，优先已打标签的歌曲
        pass  # 当前 LibrarySong 无 dance_style 字段，后续可扩展

    songs = query.order_by(LibrarySong.energy.desc().nullslast(), LibrarySong.created_at.desc()).all()
    if not songs:
        return []

    sequence = build_practice_list(songs, target_duration)
    return [
        PracticeTrackItem(
            id=s.id,
            title=s.title,
            artist=s.artist,
            bpm=s.bpm,
            camelot_key=s.camelot_key,
            energy=s.energy,
            duration=s.duration or 0,
        )
        for s in sequence
    ]
