from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class Playlist(Base):
    """歌单主表"""
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PlaylistTrack(Base):
    """歌单内歌曲及 DJ 播放配置表 (模块分离的核心)"""
    __tablename__ = "playlist_tracks"

    id = Column(Integer, primary_key=True, index=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), index=True, nullable=False)
    track_id = Column(Integer, ForeignKey("tracks.id"), index=True, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0) # 播放顺序
    
    # --- P2 核心：DJ 与练习模式配置 ---
    sync_bpm = Column(Boolean, default=False) # 是否开启 BPM 自动对齐
    transition_type = Column(String, default="none") # 过渡效果：none(直接切), fade(淡入淡出), cut_drop(Drop点切入)
    transition_duration = Column(Integer, default=0) # 过渡时长(毫秒)
    
    added_at = Column(DateTime(timezone=True), server_default=func.now())
