from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from core.database import Base
from sqlalchemy import ForeignKey

class Track(Base):
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True, nullable=False) # 文件名或歌曲名
    original_url = Column(String, nullable=False)         # 原曲在 NAS 的相对路径
    
    # P0 产生的特征数据 (允许为空，因为可能是后续分析出来的)
    bpm = Column(Float, nullable=True)
    music_key = Column(String, nullable=True)             # 避免和 SQL 关键字 key 冲突
    
    # P1 产生的拆轨数据 (允许为空)
    vocals_url = Column(String, nullable=True)
    drums_url = Column(String, nullable=True)
    bass_url = Column(String, nullable=True)
    other_url = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())



class TrackCue(Base):
    __tablename__ = "track_cues"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    track_id = Column(Integer, ForeignKey("tracks.id"), index=True, nullable=False)
    
    cue_type = Column(String, nullable=False) # "cue" (单点) 或 "ab_loop" (段落)
    start_time = Column(Float, nullable=False) # 记录秒数，如 15.5
    end_time = Column(Float, nullable=True)    # 仅 A-B 循环需要，单点为空
    name = Column(String, nullable=True)       # 用户可以给这个点起名，比如 "Drop 爆发"
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())