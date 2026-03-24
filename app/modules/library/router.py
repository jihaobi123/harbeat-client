from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.library.schemas import (
    LibrarySongCreateRequest,
    LibrarySongData,
    LibrarySongListData,
    LibrarySongUpdateRequest,
)
from app.modules.library.service import (
    create_or_replace_library_song,
    delete_library_song,
    list_library_songs,
    update_library_song,
)
from app.shared.database import get_db
from app.shared.responses import APIResponse

router = APIRouter()


@router.get("/songs", response_model=APIResponse[LibrarySongListData])
def list_library_songs_endpoint(user_id: int, db: Session = Depends(get_db)):
    songs = list_library_songs(db, user_id)
    return APIResponse(data=LibrarySongListData(songs=[LibrarySongData.model_validate(song) for song in songs]))


@router.post("/songs", response_model=APIResponse[LibrarySongData])
def create_library_song_endpoint(payload: LibrarySongCreateRequest, db: Session = Depends(get_db)):
    song = create_or_replace_library_song(db, payload)
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.patch("/songs/{song_id}", response_model=APIResponse[LibrarySongData])
def update_library_song_endpoint(
    song_id: str,
    payload: LibrarySongUpdateRequest,
    db: Session = Depends(get_db),
):
    song = update_library_song(db, song_id, payload)
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.delete("/songs/{song_id}", response_model=APIResponse[dict])
def delete_library_song_endpoint(song_id: str, db: Session = Depends(get_db)):
    delete_library_song(db, song_id)
    return APIResponse(data={"success": True})
