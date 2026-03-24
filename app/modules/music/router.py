from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.music.schemas import CueCreateRequest, CueData, SongData, SongListData, SongTagUpdateRequest
from app.modules.music.service import create_cue, get_song_or_404, list_cues, list_songs, serialize_song, update_song_tags
from app.shared.database import get_db
from app.shared.responses import APIResponse

router = APIRouter()


@router.get("/songs", response_model=APIResponse[SongListData])
def list_songs_endpoint(db: Session = Depends(get_db)):
    return APIResponse(data=SongListData(songs=list_songs(db)))


@router.get("/songs/{song_id}", response_model=APIResponse[SongData])
def get_song_endpoint(song_id: int, db: Session = Depends(get_db)):
    song = get_song_or_404(db, song_id)
    return APIResponse(data=serialize_song(song))


@router.patch("/songs/{song_id}/tags", response_model=APIResponse[SongData])
def update_song_tags_endpoint(song_id: int, payload: SongTagUpdateRequest, db: Session = Depends(get_db)):
    return APIResponse(data=update_song_tags(db, song_id, payload))


@router.post("/songs/{song_id}/cues", response_model=APIResponse[CueData])
def create_cue_endpoint(song_id: int, payload: CueCreateRequest, db: Session = Depends(get_db)):
    return APIResponse(data=create_cue(db, payload.model_copy(update={"song_id": song_id})))


@router.get("/songs/{song_id}/cues", response_model=APIResponse[list[CueData]])
def list_cues_endpoint(song_id: int, user_id: int, db: Session = Depends(get_db)):
    return APIResponse(data=list_cues(db, song_id, user_id))
