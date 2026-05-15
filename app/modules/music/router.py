import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.modules.music.schemas import (
    CueCreateRequest,
    CueData,
    SongData,
    SongListData,
    SongProcessRequest,
    SongProcessResult,
    SongTagUpdateRequest,
    UpsertSongRequest,
)
from app.modules.music.service import (
    create_cue,
    get_song_or_404,
    list_cues,
    list_songs,
    process_song_for_styles,
    search_songs,
    serialize_song,
    update_song_tags,
    upsert_song_with_tags,
)
from app.modules.music.transition_stems import get_stem_library
from app.shared.database import get_db
from app.shared.responses import APIResponse

router = APIRouter()


# ───────────────────── MC Flourish SFX (人工加花) ─────────────────────
# Five distinct synthesis-based flourish sounds, reusing the pre-rendered
# transition stem library. Each name is a one-shot DJ-style accent that the
# user can trigger on-demand from the MixLab UI.

_FLOURISH_TYPES: list[dict[str, str]] = [
    {"id": "impact",         "label": "Impact",        "stem_type": "impact",         "energy": "high"},
    {"id": "drum_fill",      "label": "Drum Fill",     "stem_type": "drum_fill",      "energy": "medium"},
    {"id": "riser",          "label": "Riser",         "stem_type": "riser",          "energy": "high"},
    {"id": "reverse_cymbal", "label": "Reverse Cymbal","stem_type": "reverse_cymbal", "energy": "medium"},
    {"id": "ambient_pad",    "label": "Ambient Pad",   "stem_type": "ambient_pad",    "energy": "low"},
]


def _flourish_descriptor(item: dict[str, str]) -> dict[str, object] | None:
    library = get_stem_library()
    candidates = [s for s in library.by_type(item["stem_type"]) if s.energy == item["energy"]]
    if not candidates:
        candidates = library.by_type(item["stem_type"])
    if not candidates:
        return None
    stem = candidates[0]
    return {
        "id": item["id"],
        "label": item["label"],
        "stem_type": stem.stem_type,
        "energy": stem.energy,
        "duration_sec": round(stem.duration_sec, 3),
        "bars": stem.bars,
        "stream_url": f"/api/music/flourish/{item['id']}",
    }


@router.get("/flourish", response_model=APIResponse[dict])
def list_flourish_sfx():
    """List the 5 available MC flourish SFX clips (human-triggered accents)."""
    items = [d for d in (_flourish_descriptor(t) for t in _FLOURISH_TYPES) if d is not None]
    return APIResponse(data={"items": items})


@router.get("/flourish/{flourish_id}")
def stream_flourish_sfx(flourish_id: str):
    match = next((t for t in _FLOURISH_TYPES if t["id"] == flourish_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="flourish id not found")
    library = get_stem_library()
    candidates = [s for s in library.by_type(match["stem_type"]) if s.energy == match["energy"]]
    if not candidates:
        candidates = library.by_type(match["stem_type"])
    if not candidates or not os.path.isfile(candidates[0].file_path):
        raise HTTPException(status_code=404, detail="flourish stem file missing")
    return FileResponse(
        candidates[0].file_path,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/songs", response_model=APIResponse[SongListData])
def list_songs_endpoint(db: Session = Depends(get_db)):
    return APIResponse(data=SongListData(songs=list_songs(db)))


@router.get("/songs/search", response_model=APIResponse[SongListData])
def search_songs_endpoint(q: str = Query("", min_length=1), db: Session = Depends(get_db)):
    return APIResponse(data=SongListData(songs=search_songs(db, q)))


@router.get("/songs/{song_id}", response_model=APIResponse[SongData])
def get_song_endpoint(song_id: int, db: Session = Depends(get_db)):
    song = get_song_or_404(db, song_id)
    return APIResponse(data=serialize_song(song))


@router.patch("/songs/{song_id}/tags", response_model=APIResponse[SongData])
def update_song_tags_endpoint(song_id: int, payload: SongTagUpdateRequest, db: Session = Depends(get_db)):
    return APIResponse(data=update_song_tags(db, song_id, payload))


@router.post("/songs/upsert", response_model=APIResponse[SongData])
def upsert_song_endpoint(payload: UpsertSongRequest, db: Session = Depends(get_db)):
    return APIResponse(data=upsert_song_with_tags(db, payload))


@router.post("/songs/{song_id}/cues", response_model=APIResponse[CueData])
def create_cue_endpoint(song_id: int, payload: CueCreateRequest, db: Session = Depends(get_db)):
    return APIResponse(data=create_cue(db, payload.model_copy(update={"song_id": song_id})))


@router.get("/songs/{song_id}/cues", response_model=APIResponse[list[CueData]])
def list_cues_endpoint(song_id: int, user_id: int, db: Session = Depends(get_db)):
    return APIResponse(data=list_cues(db, song_id, user_id))


@router.post("/songs/{song_id}/process-style", response_model=APIResponse[SongProcessResult])
def process_song_style_endpoint(song_id: int, payload: SongProcessRequest, db: Session = Depends(get_db)):
    """对单曲生成多风格街舞成品。"""
    result = process_song_for_styles(db, song_id, payload)
    return APIResponse(data=result)
