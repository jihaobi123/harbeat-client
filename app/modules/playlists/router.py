from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.responses import APIResponse
from app.modules.playlists.schemas import PlaylistImportData, PlaylistImportRequest
from app.modules.playlists.service import import_playlist

router = APIRouter()


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
