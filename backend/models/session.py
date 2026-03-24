from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class PracticeSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False) # 对应前端传来的 user_id
    mode = Column(String, nullable=False)                 # 例如 "practice", "battle"
    
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)

class SessionEvent(Base):
    __tablename__ = "session_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True, nullable=False)
    
    event_type = Column(String, nullable=False)   # 例如 "cue_mark", "ab_loop", "skip"
    event_value = Column(String, nullable=True)   # 例如 "time=01:15.5", "start=10,end=30"
    client_timestamp = Column(DateTime(timezone=True), nullable=False) # 前端上报的时间戳
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())