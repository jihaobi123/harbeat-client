from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.playlists.schemas import (
    DjMixPlanRequest,
    DjMixPlanResult,
    DjOfflineMixRequest,
    DjOfflineMixResult,
    PlaylistDetailData,
    PlaylistImportData,
    PlaylistImportRequest,
    PlaylistListData,
    PlaylistReorderRequest,
    PlaylistSongTagUpdateRequest,
    StyleMixRequest,
    StyleMixResult,
)
from app.modules.playlists.service import (
    add_library_songs_to_playlist,
    build_asset_manifest,
    create_empty_playlist,
    delete_playlist,
    generate_dj_mix_plan,
    generate_dj_offline_mix,
    generate_style_mix_playlist,
    get_playlist_detail,
    import_playlist,
    list_playlists,
    reorder_playlist_songs,
    update_playlist_song_tags,
)
from app.modules.users.models import User
from app.shared.database import get_db
from app.shared.responses import APIResponse

router = APIRouter()


class CreatePlaylistRequest(BaseModel):
    name: str


class AddSongsRequest(BaseModel):
    library_song_ids: list[str]


# ── App compatibility aliases ──

@router.post("/create-empty", response_model=APIResponse[dict])
def create_empty_playlist_alias(
    payload: CreatePlaylistRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    playlist = create_empty_playlist(db, current_user.id, payload.name)
    return APIResponse(data={"id": playlist.id, "playlist_name": playlist.playlist_name})


@router.post("/{playlist_id:int}/add-library-songs", response_model=APIResponse[dict])
def add_library_songs_alias(
    playlist_id: int,
    payload: AddSongsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = add_library_songs_to_playlist(db, playlist_id, current_user.id, payload.library_song_ids)
    return APIResponse(data={"added": count})


@router.post("/import", response_model=APIResponse[PlaylistImportData])
def import_playlist_endpoint(payload: PlaylistImportRequest, db: Session = Depends(get_db)):
    playlist, pending_analysis_count = import_playlist(db, payload)
    return APIResponse(
        data=PlaylistImportData(
            playlist_id=playlist.id,
            import_count=len(payload.songs),
            pending_analysis_count=pending_analysis_count,
        )
    )


@router.get("", response_model=APIResponse[PlaylistListData])
def list_playlists_endpoint(user_id: int, db: Session = Depends(get_db)):
    return APIResponse(data=list_playlists(db, user_id))


@router.get("/{playlist_id:int}", response_model=APIResponse[PlaylistDetailData])
def get_playlist_detail_endpoint(playlist_id: int, db: Session = Depends(get_db)):
    return APIResponse(data=get_playlist_detail(db, playlist_id))


@router.delete("/{playlist_id:int}", response_model=APIResponse[dict])
def delete_playlist_endpoint(playlist_id: int, db: Session = Depends(get_db)):
    delete_playlist(db, playlist_id)
    return APIResponse(data={"success": True})


@router.patch("/{playlist_id:int}/songs/{song_id:int}/tags", response_model=APIResponse[dict])
def update_playlist_song_tags_endpoint(
    playlist_id: int,
    song_id: int,
    payload: PlaylistSongTagUpdateRequest,
    db: Session = Depends(get_db),
):
    update_playlist_song_tags(db, playlist_id, song_id, payload.tags)
    return APIResponse(data={"success": True})


@router.post("/create", response_model=APIResponse[dict])
def create_playlist_endpoint(
    payload: CreatePlaylistRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    playlist = create_empty_playlist(db, current_user.id, payload.name)
    return APIResponse(data={"id": playlist.id, "playlist_name": playlist.playlist_name})


@router.post("/{playlist_id:int}/add-songs", response_model=APIResponse[dict])
def add_songs_to_playlist_endpoint(
    playlist_id: int,
    payload: AddSongsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = add_library_songs_to_playlist(db, playlist_id, current_user.id, payload.library_song_ids)
    return APIResponse(data={"added": count})


@router.put("/{playlist_id:int}/reorder", response_model=APIResponse[dict])
def reorder_playlist_endpoint(
    playlist_id: int,
    payload: PlaylistReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reorder_playlist_songs(db, playlist_id, current_user.id, payload)
    return APIResponse(data={"success": True})


@router.post("/generate-style-mix", response_model=APIResponse[StyleMixResult])
def generate_style_mix_endpoint(
    payload: StyleMixRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成风格化连续练舞歌单。"""
    result = generate_style_mix_playlist(db, payload, user_id=current_user.id)
    return APIResponse(data=result)


@router.post("/generate-dj-mix-plan", response_model=APIResponse[DjMixPlanResult])
def generate_dj_mix_plan_endpoint(
    payload: DjMixPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI DJ 混音编排：智能排序 + Camelot 调性匹配 + 转场计划。"""
    payload.user_id = current_user.id
    result = generate_dj_mix_plan(db, payload)
    return APIResponse(data=result)


@router.post("/generate-dj-offline-mix", response_model=APIResponse[DjOfflineMixResult])
def generate_dj_offline_mix_endpoint(
    payload: DjOfflineMixRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """离线渲染 DJ mix：stem-aware 转场 + WAV/MP3 导出。"""
    payload.user_id = current_user.id
    result = generate_dj_offline_mix(db, payload)
    return APIResponse(data=result)


# ─── Cypher: AssetManifest + cached MixPlan + SSE planner ────────────────

@router.get("/{playlist_id:int}/manifest", response_model=APIResponse[dict])
def get_playlist_manifest_endpoint(
    playlist_id: int,
    plan_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cypher 协议 P3 AssetManifest。返回 playlist 中每首歌的下载清单 + sha256。

    若任何一首歌 analysis_status != 'completed'，返回 409 + 未 ready 列表。
    """
    manifest = build_asset_manifest(db, playlist_id, current_user.id, plan_id=plan_id)
    return APIResponse(data=manifest)


@router.get("/{playlist_id:int}/mix-plan/latest", response_model=APIResponse[dict])
def get_latest_mix_plan_endpoint(
    playlist_id: int,
    current_user: User = Depends(get_current_user),
):
    """Cypher 协议 P2 MixPlan：返回 Redis 中缓存的最近一次 dj-mix 结果。"""
    from app.shared.redis import get_redis
    import json
    key = f"harbeat:mix_plan:latest:{current_user.id}:{playlist_id}"
    raw = get_redis().get(key)
    if not raw:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="no cached mix plan; call /dj-mix-stream first")
    return APIResponse(data=json.loads(raw))


@router.post("/{playlist_id:int}/dj-mix-stream")
def dj_mix_plan_stream_endpoint(
    playlist_id: int,
    payload: DjMixPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SSE 流式 dj-mix-plan。首次未命中缓存时同步计算，命中即时返回。

    事件流：
      event: plan_started   data: {playlist_id, cache_hit:bool}
      event: plan_final     data: {<MixPlan>, score:float, elapsed_sec:float}
      event: error          data: {message:str}
    """
    import json
    import time
    from fastapi.responses import StreamingResponse
    from app.shared.redis import get_redis

    payload.user_id = current_user.id
    payload.playlist_id = playlist_id

    redis_client = get_redis()
    cache_key = f"harbeat:mix_plan:latest:{current_user.id}:{playlist_id}"

    def _generator():
        t0 = time.time()
        try:
            cached = redis_client.get(cache_key)
            if cached:
                yield f"event: plan_started\ndata: {json.dumps({'playlist_id': playlist_id, 'cache_hit': True})}\n\n"
                yield f"event: plan_final\ndata: {cached}\n\n"
                return

            yield f"event: plan_started\ndata: {json.dumps({'playlist_id': playlist_id, 'cache_hit': False})}\n\n"
            result = generate_dj_mix_plan(db, payload)
            payload_out = {
                "playlist_id": playlist_id,
                "result": json.loads(result.model_dump_json()),
                "elapsed_sec": round(time.time() - t0, 2),
            }
            redis_client.setex(cache_key, 7 * 86400, json.dumps(payload_out))
            yield f"event: plan_final\ndata: {json.dumps(payload_out)}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(_generator(), media_type="text/event-stream")
