from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import aliased

from schemas.playlist import StandardResponse, AddTrackRequest, PlaylistDetailData, PlaylistItemData
from models.playlist import Playlist, PlaylistTrack
from models.track import Track  # 跨模块引用模型(仅用于读查询，符合规范)
from core.database import get_db_session

router = APIRouter(prefix="/api/playlists", tags=["Playlist & DJ Module"])

@router.post("/", response_model=StandardResponse)
async def create_playlist(name: str, user_id: int, db: AsyncSession = Depends(get_db_session)):
    """创建一个新歌单"""
    try:
        new_playlist = Playlist(name=name, user_id=user_id)
        db.add(new_playlist)
        await db.commit()
        await db.refresh(new_playlist)
        return StandardResponse(data={"playlist_id": new_playlist.id})
    except Exception as e:
        return StandardResponse(code=-1, message=str(e))

@router.post("/{playlist_id}/tracks", response_model=StandardResponse)
async def add_track_to_playlist(
    playlist_id: int, 
    req: AddTrackRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    """将歌曲加入歌单，并配置 BPM Sync 和 DJ 过渡效果"""
    try:
        new_pt = PlaylistTrack(
            playlist_id=playlist_id,
            track_id=req.track_id,
            sort_order=req.sort_order,
            sync_bpm=req.sync_bpm,
            transition_type=req.transition_type,
            transition_duration=req.transition_duration
        )
        db.add(new_pt)
        await db.commit()
        return StandardResponse(message="歌曲及 DJ 配置已添加到歌单")
    except Exception as e:
        return StandardResponse(code=-1, message=str(e))

@router.get("/{playlist_id}", response_model=StandardResponse)
async def get_playlist(playlist_id: int, db: AsyncSession = Depends(get_db_session)):
    """获取歌单详情（包含 DJ 配置和用于前端计算的 BPM）"""
    try:
        playlist_query = await db.execute(select(Playlist).where(Playlist.id == playlist_id))
        playlist = playlist_query.scalars().first()
        if not playlist:
            return StandardResponse(code=-1, message="歌单不存在")

        # 连表查询：PlaylistTrack (查配置) + Track (查 BPM 和 URL)
        query = await db.execute(
            select(PlaylistTrack, Track)
            .join(Track, PlaylistTrack.track_id == Track.id)
            .where(PlaylistTrack.playlist_id == playlist_id)
            .order_by(PlaylistTrack.sort_order)
        )
        results = query.all()

        track_items = []
        for pt, track in results:
            track_items.append(PlaylistItemData(
                playlist_track_id=pt.id,
                track_id=pt.track_id,
                sort_order=pt.sort_order,
                sync_bpm=pt.sync_bpm,
                transition_type=pt.transition_type,
                transition_duration=pt.transition_duration,
                bpm=track.bpm,             # 前端拿到这个 BPM 才能算拉伸比例
                original_url=track.original_url
            ))

        data = PlaylistDetailData(playlist_id=playlist.id, name=playlist.name, tracks=track_items)
        return StandardResponse(data=data)
    except Exception as e:
        return StandardResponse(code=-1, message=str(e))
        