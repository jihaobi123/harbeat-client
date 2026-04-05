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


@router.patch("/{playlist_id:int}/reorder", response_model=APIResponse[dict])
def reorder_playlist_endpoint(
    playlist_id: int,
    payload: PlaylistReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reorder_playlist_songs(db, playlist_id, current_user.id, payload)
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


@router.post("/generate-style-mix", response_model=APIResponse[StyleMixResult])
def generate_style_mix_endpoint(
    payload: StyleMixRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """鐢熸垚椋庢牸鍖栬繛缁粌鑸炴瓕鍗曘€?"""
    result = generate_style_mix_playlist(db, payload, user_id=current_user.id)
    return APIResponse(data=result)


@router.post("/generate-dj-mix-plan", response_model=APIResponse[DjMixPlanResult])
def generate_dj_mix_plan_endpoint(
    payload: DjMixPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = generate_dj_mix_plan(db, payload.model_copy(update={"user_id": current_user.id}))
    return APIResponse(data=result)


@router.post("/generate-dj-offline-mix", response_model=APIResponse[DjOfflineMixResult])
def generate_dj_offline_mix_endpoint(
    payload: DjOfflineMixRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = generate_dj_offline_mix(db, payload.model_copy(update={"user_id": current_user.id}))
    return APIResponse(data=result)

