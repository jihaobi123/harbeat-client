from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.responses import APIResponse
from app.modules.auth.dependencies import get_current_user
from app.modules.users.models import User
from app.modules.playlists.schemas import (
    PlaylistDetailData,
    PlaylistImportData,
    PlaylistImportRequest,
    PlaylistListData,
    PlaylistSongTagUpdateRequest,
)
from app.modules.playlists.service import (
    create_empty_playlist,
    add_library_songs_to_playlist,
    delete_playlist,
    get_playlist_detail,
    import_playlist,
    list_playlists,
    update_playlist_song_tags,
)

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


@router.get("/{playlist_id}", response_model=APIResponse[PlaylistDetailData])
def get_playlist_detail_endpoint(playlist_id: int, db: Session = Depends(get_db)):
    return APIResponse(data=get_playlist_detail(db, playlist_id))


@router.delete("/{playlist_id}", response_model=APIResponse[dict])
def delete_playlist_endpoint(playlist_id: int, db: Session = Depends(get_db)):
    delete_playlist(db, playlist_id)
    return APIResponse(data={"success": True})


@router.patch("/{playlist_id}/songs/{song_id}/tags", response_model=APIResponse[dict])
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
    """Create an empty playlist."""
    playlist = create_empty_playlist(db, current_user.id, payload.name)
    return APIResponse(data={
        "id": playlist.id,
        "playlist_name": playlist.playlist_name,
    })


@router.post("/{playlist_id}/add-songs", response_model=APIResponse[dict])
def add_songs_to_playlist_endpoint(
    playlist_id: int,
    payload: AddSongsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add library songs to a playlist."""
    count = add_library_songs_to_playlist(db, playlist_id, current_user.id, payload.library_song_ids)
    return APIResponse(data={"added": count})
