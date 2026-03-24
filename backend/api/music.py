from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from schemas.music import StandardResponse, AnalyzeData, SplitData
from services.audio_service import analyze_audio_service, separate_stems_service, NAS_RAW_DIR
from core.database import get_db_session
from models.track import Track
import shutil
import os

from models.track import TrackCue
from schemas.music import CueCreateRequest, CueResponseData


router = APIRouter(prefix="/api/music", tags=["Music Tags Module"])

@router.post("/analyze", response_model=StandardResponse)
async def analyze(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session)  # 注入数据库
):
    # 1. 保存文件到本地 NAS
    file_path = os.path.join(NAS_RAW_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        # 2. 调用核心算法算 BPM 和 Key
        result = analyze_audio_service(file_path)
        
        # 3. 将结果作为一条新记录存入 PostgreSQL
        new_track = Track(
            filename=file.filename,
            original_url=f"/uploads/raw/{file.filename}",
            bpm=result["bpm"],
            music_key=result["key"]
        )
        db.add(new_track)
        await db.commit()
        await db.refresh(new_track) # 获取数据库自动分配的 ID
        
        # 4. 返回带 ID 的结果给前端
        data = AnalyzeData(track_id=new_track.id, **result)
        return StandardResponse(code=0, message="分析完成并存入数据库", data=data)
        
    except Exception as e:
        return StandardResponse(code=-1, message=str(e))


@router.post("/split", response_model=StandardResponse)
async def split(
    track_id: int, # 【核心改动】：MVP 阶段直接接收数据库 ID 进行拆轨
    db: AsyncSession = Depends(get_db_session)
):
    # 1. 从数据库中查出这首歌
    query = await db.execute(select(Track).where(Track.id == track_id))
    track = query.scalars().first()
    
    if not track:
        return StandardResponse(code=-1, message="找不到该歌曲记录")
        
    # 2. 拿到当时存入的物理路径
    local_file_path = os.path.join(NAS_RAW_DIR, track.filename)
    
    try:
        # 3. 调用拆轨算法
        result = separate_stems_service(local_file_path)
        stems = result["stems"]
        
        # 4. 把拆出来的 4 条音轨 URL 更新到刚刚那条数据库记录里
        track.vocals_url = stems["vocals_url"]
        track.drums_url = stems["drums_url"]
        track.bass_url = stems["bass_url"]
        track.other_url = stems["other_url"]
        await db.commit()
        
        data = SplitData(**stems)
        return StandardResponse(code=0, message="拆轨完成并更新数据库", data=data)
        
    except Exception as e:
        return StandardResponse(code=-1, message=str(e))




@router.post("/cues", response_model=StandardResponse)
async def save_track_cue(req: CueCreateRequest, db: AsyncSession = Depends(get_db_session)):
    """保存用户在一首歌里的 Cue 点或 A-B 段"""
    try:
        new_cue = TrackCue(**req.dict())
        db.add(new_cue)
        await db.commit()
        await db.refresh(new_cue)
        return StandardResponse(code=0, message="Cue点保存成功", data={"cue_id": new_cue.id})
    except Exception as e:
        return StandardResponse(code=-1, message=str(e))

@router.get("/{track_id}/cues", response_model=StandardResponse)
async def get_track_cues(track_id: int, user_id: int, db: AsyncSession = Depends(get_db_session)):
    """获取一首歌所有的 Cue 点和 A-B 段 (供前端一打开播放器时加载)"""
    try:
        query = await db.execute(
            select(TrackCue).where(TrackCue.track_id == track_id, TrackCue.user_id == user_id)
        )
        cues = query.scalars().all()
        
        # 组装返回列表
        cues_data = [CueResponseData(
            id=c.id, cue_type=c.cue_type, start_time=c.start_time, end_time=c.end_time, name=c.name
        ) for c in cues]
        
        return StandardResponse(data=cues_data)
    except Exception as e:
        return StandardResponse(code=-1, message=str(e))