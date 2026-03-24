from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone

from schemas.session import (
    StandardResponse, SessionStartRequest, SessionStartData, 
    SessionEventRequest, SuccessData, SessionEndRequest
)
from models.session import PracticeSession, SessionEvent
from core.database import get_db_session

router = APIRouter(prefix="/api/sessions", tags=["Session & Event Tracking Module"])

@router.post("/start", response_model=StandardResponse)
async def start_session(req: SessionStartRequest, db: AsyncSession = Depends(get_db_session)):
    """6.7 创建播放会话"""
    try:
        new_session = PracticeSession(
            user_id=req.user_id,
            mode=req.mode
        )
        db.add(new_session)
        await db.commit()
        await db.refresh(new_session)
        
        return StandardResponse(data=SessionStartData(session_id=new_session.id))
    except Exception as e:
        return StandardResponse(code=-1, message=str(e))

@router.post("/event", response_model=StandardResponse)
async def report_event(req: SessionEventRequest, db: AsyncSession = Depends(get_db_session)):
    """6.8 上报播放事件 (标记Cue点、设置A-B循环等)"""
    try:
        new_event = SessionEvent(
            session_id=req.session_id,
            event_type=req.event_type,
            event_value=req.event_value,
            client_timestamp=req.timestamp
        )
        db.add(new_event)
        await db.commit()
        
        return StandardResponse(data=SuccessData())
    except Exception as e:
        return StandardResponse(code=-1, message=str(e))

@router.post("/end", response_model=StandardResponse)
async def end_session(req: SessionEndRequest, db: AsyncSession = Depends(get_db_session)):
    """6.9 结束播放会话"""
    try:
        query = await db.execute(select(PracticeSession).where(PracticeSession.id == req.session_id))
        session_record = query.scalars().first()
        
        if session_record:
            # 记录结束时间 (UTC)
            session_record.end_time = datetime.now(timezone.utc)
            await db.commit()
            
        return StandardResponse(data=SuccessData())
    except Exception as e:
        return StandardResponse(code=-1, message=str(e))