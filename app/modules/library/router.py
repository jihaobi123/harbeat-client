import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.library.schemas import (
    BeatCorrectionRequest,
    DanceStyleClassifyRequest,
    LibrarySongCreateRequest,
    LibrarySongData,
    LibrarySongListData,
    LibrarySongUpdateRequest,
)
from app.modules.library.service import (
    create_or_replace_library_song,
    delete_library_song,
    list_library_songs,
    search_library_songs,
    update_library_song,
)
from app.modules.users.models import User
from app.shared.config import get_settings
from app.shared.database import get_db
from app.shared.responses import APIResponse

router = APIRouter()

ALLOWED_FORMATS = {"mp3", "flac", "wav", "ogg", "aac", "m4a", "opus", "wma", "ncm"}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB


class ReanalyzeAllRequest(BaseModel):
    force: bool = False
    limit: int = Field(default=50, ge=1, le=500)


@router.get("/songs", response_model=APIResponse[LibrarySongListData])
def list_library_songs_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    songs = list_library_songs(db, current_user.id)
    return APIResponse(data=LibrarySongListData(songs=[LibrarySongData.model_validate(song) for song in songs]))


@router.post("/reanalyze-all", response_model=APIResponse[dict])
def reanalyze_all_endpoint(
    payload: ReanalyzeAllRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue analysis for the current user's imported/downloaded songs."""
    from app.modules.library.models import LibrarySong
    from app.modules.library.background_tasks import run_analysis_and_separation

    rows = (
        db.query(LibrarySong)
        .filter(
            LibrarySong.user_id == current_user.id,
            LibrarySong.source_path.isnot(None),
            LibrarySong.source_path != "",
        )
        .order_by(LibrarySong.created_at.desc())
        .limit(payload.limit)
        .all()
    )

    updated = 0
    skipped = 0
    failed: list[dict] = []
    for song in rows:
        if not payload.force and song.analysis_status == "completed":
            skipped += 1
            continue
        if not os.path.isfile(song.source_path or ""):
            failed.append({"id": song.id, "title": song.title, "error": "audio file not found"})
            continue
        song.analysis_status = "pending"
        background_tasks.add_task(run_analysis_and_separation, song.id)
        updated += 1

    db.commit()
    return APIResponse(data={"updated": updated, "skipped": skipped, "failed": failed})


@router.get("/songs/search", response_model=APIResponse[LibrarySongListData])
def search_library_songs_endpoint(
    q: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    songs = search_library_songs(db, current_user.id, q)
    return APIResponse(data=LibrarySongListData(songs=[LibrarySongData.model_validate(song) for song in songs]))


@router.get("/songs/needs-review", response_model=APIResponse[LibrarySongListData])
def list_needs_review_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List songs with low beat confidence that need manual review."""
    from app.modules.library.models import LibrarySong

    songs = (
        db.query(LibrarySong)
        .filter(LibrarySong.user_id == current_user.id, LibrarySong.beat_needs_review == 1)
        .all()
    )
    return APIResponse(data=LibrarySongListData(songs=[LibrarySongData.model_validate(s) for s in songs]))


@router.get("/songs/{song_id}", response_model=APIResponse[LibrarySongData])
def get_library_song_endpoint(
    song_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.modules.library.models import LibrarySong
    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    if song.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your song")
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.post("/songs", response_model=APIResponse[LibrarySongData])
def create_library_song_endpoint(
    payload: LibrarySongCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload.user_id = current_user.id
    song = create_or_replace_library_song(db, payload)
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.post("/upload", response_model=APIResponse[LibrarySongData])
def upload_audio_endpoint(
    file: UploadFile = File(...),
    title: str = Form(""),
    artist: str = Form("Unknown Artist"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no file provided")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported format: {ext}. allowed: {', '.join(sorted(ALLOWED_FORMATS))}",
        )

    settings = get_settings()
    upload_dir = os.path.abspath(settings.upload_dir)
    user_dir = os.path.join(upload_dir, str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)

    song_id = uuid.uuid4().hex
    filename = f"{song_id}.{ext}"
    file_path = os.path.join(user_dir, filename)

    size = 0
    with open(file_path, "wb") as out:
        while True:
            chunk = file.file.read(1024 * 64)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                out.close()
                os.remove(file_path)
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file too large (max 200MB)")
            out.write(chunk)

    if not title:
        title = file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename

    # Handle NCM (NetEase encrypted) files
    if ext == "ncm":
        try:
            from app.modules.library.ncm_decrypt import decrypt_ncm
            ncm_result = decrypt_ncm(file_path, output_dir=user_dir)
            # Use decrypted file instead
            os.remove(file_path)
            file_path = ncm_result["audio_path"]
            ext = ncm_result["format"]
            size = os.path.getsize(file_path)
            if not title or title == file.filename.rsplit(".", 1)[0]:
                title = ncm_result["title"]
            if artist == "Unknown Artist":
                artist = ncm_result["artist"]
        except Exception as e:
            os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"NCM decryption failed: {e}",
            )

    from app.modules.library.schemas import LibrarySongCreateRequest
    from datetime import datetime

    payload = LibrarySongCreateRequest(
        id=song_id,
        user_id=current_user.id,
        title=title,
        artist=artist,
        duration=0,
        format=ext,
        file_size=size,
        source_type="upload",
        source_path=file_path,
        created_at=datetime.utcnow(),
    )
    song = create_or_replace_library_song(db, payload)
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.patch("/songs/{song_id}", response_model=APIResponse[LibrarySongData])
def update_library_song_endpoint(
    song_id: str,
    payload: LibrarySongUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    song = update_library_song(db, song_id, payload)
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.delete("/songs/{song_id}", response_model=APIResponse[dict])
def delete_library_song_endpoint(
    song_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    delete_library_song(db, song_id, current_user.id)
    return APIResponse(data={"success": True})


@router.post("/songs/{song_id}/analyze", response_model=APIResponse[LibrarySongData])
def analyze_library_song_endpoint(
    song_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.modules.library.models import LibrarySong
    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    if song.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your song")
    if not song.source_path or not os.path.isfile(song.source_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio file not found on disk")

    try:
        from app.modules.library.analysis import analyze_audio_file
        result = analyze_audio_file(
            song.source_path,
            title=song.title or "",
            artist=song.artist or "",
        )
    except Exception as e:
        song.analysis_status = "error"
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"analysis failed: {e}")

    song.bpm = result["bpm"]
    song.duration = result["duration"]
    song.key = result.get("key")
    song.camelot_key = result.get("camelot_key")
    song.energy = result.get("energy")
    song.genres = result.get("genres", [])
    song.genre_status = result.get("genre_status", "none")
    song.genre_source = result.get("genre_source")
    song.music_features = result.get("music_features", {})
    song.dance_styles = result.get("dance_styles", [])
    song.dance_style_scores = result.get("dance_style_scores", {})
    song.dance_style_status = result.get("dance_style_status", "none")
    song.classifier_params = result.get("classifier_params", {})
    song.classifier_version = result.get("classifier_version")
    song.beat_points = result.get("beat_points", [])
    song.beat_confidence = result.get("beat_confidence")
    song.beat_grid_offset = result.get("beat_grid_offset")
    song.beat_grid_interval = result.get("beat_grid_interval")
    song.beat_engines_used = result.get("beat_engines_used", [])
    song.beat_needs_review = int(result.get("beat_needs_review", False))
    # Add IDs to cue points for frontend
    raw_cues = result.get("cue_points", [])
    song.cue_points = [
        {"id": f"cue-{song_id}-{i}", "time": c["time"], "label": c["label"], "color": c["color"]}
        for i, c in enumerate(raw_cues)
    ]
    song.analysis_status = "completed"
    db.commit()
    db.refresh(song)
    return APIResponse(data=LibrarySongData.model_validate(song))


def _get_owned_library_song(db: Session, song_id: str, user_id: int):
    from app.modules.library.models import LibrarySong

    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    if song.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your song")
    return song


@router.post("/songs/{song_id}/classify-dance-styles", response_model=APIResponse[LibrarySongData])
def classify_dance_styles_endpoint(
    song_id: str,
    payload: DanceStyleClassifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    song = _get_owned_library_song(db, song_id, current_user.id)

    try:
        from app.modules.library.dance_style_classifier import classify_dance_styles
        classification = classify_dance_styles(
            genres=song.genres or [],
            bpm=song.bpm,
            energy=song.energy,
            beat_confidence=song.beat_confidence,
            beat_points=song.beat_points or [],
            phrase_map=song.phrase_map or [],
            params=payload.params,
            top_k=payload.top_k,
            threshold=payload.threshold,
        )
    except Exception as exc:
        song.dance_style_status = "error"
        song.dance_style_scores = {"error": str(exc)}
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"classification failed: {exc}")

    song.music_features = classification["music_features"]
    song.dance_styles = classification["dance_styles"]
    song.dance_style_scores = classification["dance_style_scores"]
    song.dance_style_status = "completed"
    song.classifier_params = payload.params
    song.classifier_version = classification["classifier_version"]
    db.commit()
    db.refresh(song)
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.post("/songs/{song_id}/separate-stems", response_model=APIResponse[dict])
def separate_stems_endpoint(
    song_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Separate audio into stems (vocals, drums, bass, other) using demucs."""
    from app.modules.library.models import LibrarySong
    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    if song.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your song")
    if not song.source_path or not os.path.isfile(song.source_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio file not found on disk")

    import subprocess
    import sys

    stems_base = os.path.join(os.path.dirname(os.path.abspath(song.source_path)), "..", "stems")
    stems_base = os.path.abspath(stems_base)
    os.makedirs(stems_base, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(song.source_path))[0]
    stems_dir = os.path.join(stems_base, "htdemucs", base_name)
    stem_names = ["vocals", "drums", "bass", "other"]

    # Check if already separated
    if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
        stems = {s: os.path.join(stems_dir, f"{s}.wav") for s in stem_names}
        song.stems = stems
        db.commit()
        return APIResponse(data={"stems": stems})

    # Run demucs
    python_exe = sys.executable
    try:
        subprocess.run(
            [python_exe, "-m", "demucs", "-n", "htdemucs", "-o", stems_base, song.source_path],
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"stem separation failed: {e.stderr or e.stdout or str(e)}",
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="demucs not installed. Run: pip install demucs",
        )

    if not all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="stem separation completed but output files not found",
        )

    stems = {s: os.path.join(stems_dir, f"{s}.wav") for s in stem_names}
    song.stems = stems
    db.commit()
    return APIResponse(data={"stems": stems})


# ── Beat correction endpoints ─────────────────────────────────────────────


@router.post("/songs/{song_id}/correct-beats", response_model=APIResponse[LibrarySongData])
def correct_beats_endpoint(
    song_id: str,
    payload: BeatCorrectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply manual BPM/beatgrid correction from human review."""
    from app.modules.library.models import LibrarySong
    from app.modules.library.beat_engine import BeatResult, apply_manual_correction

    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    if song.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your song")

    # Reconstruct current BeatResult from DB fields
    current = BeatResult(
        bpm=song.bpm or 120.0,
        beat_points=song.beat_points or [],
        downbeats=song.downbeats or [],
        grid_offset=song.beat_grid_offset or 0.0,
        grid_interval=song.beat_grid_interval or 0.5,
        confidence=song.beat_confidence or 0.0,
        engines_used=song.beat_engines_used or [],
        needs_review=bool(song.beat_needs_review),
    )

    corrected = apply_manual_correction(
        current,
        corrected_bpm=payload.bpm,
        corrected_offset=payload.grid_offset,
        corrected_downbeat_phase=payload.downbeat_phase,
        duration=song.duration or 0.0,
    )

    song.bpm = corrected.bpm
    song.beat_points = corrected.beat_points
    song.downbeats = corrected.downbeats
    song.beat_grid_offset = corrected.grid_offset
    song.beat_grid_interval = corrected.grid_interval
    song.beat_confidence = corrected.confidence
    song.beat_engines_used = corrected.engines_used
    song.beat_needs_review = 0
    db.commit()
    db.refresh(song)
    return APIResponse(data=LibrarySongData.model_validate(song))
