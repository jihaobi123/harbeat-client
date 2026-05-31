import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
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


@router.get("/songs", response_model=APIResponse[LibrarySongListData])
def list_library_songs_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    songs = list_library_songs(db, current_user.id)
    return APIResponse(data=LibrarySongListData(songs=[LibrarySongData.model_validate(song) for song in songs]))


@router.get("/songs/search", response_model=APIResponse[LibrarySongListData])
def search_library_songs_endpoint(
    q: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    songs = search_library_songs(db, current_user.id, q)
    return APIResponse(data=LibrarySongListData(songs=[LibrarySongData.model_validate(song) for song in songs]))


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
        result = analyze_audio_file(song.source_path)
    except Exception as e:
        song.analysis_status = "error"
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"analysis failed: {e}")

    song.bpm = result["bpm"]
    song.duration = result["duration"]
    song.key = result.get("key")
    song.camelot_key = result.get("camelot_key")
    song.energy = result.get("energy")
    song.beat_points = result.get("beat_points", [])
    song.bpm_curve = result.get("bpm_curve", [])
    song.tempo_stability = result.get("tempo_stability")
    song.energy_curve = result.get("energy_curve", [])
    song.transition_windows = result.get("transition_windows", [])
    song.downbeats = result.get("downbeats", [])
    song.phrase_map = result.get("phrase_map", [])
    song.key_confidence = result.get("key_confidence")
    # Add IDs to cue points for frontend
    raw_cues = result.get("cue_points", [])
    song.cue_points = [
        {"id": f"cue-{song_id}-{i}", "time": c["time"], "label": c["label"], "color": c["color"]}
        for i, c in enumerate(raw_cues)
    ]
    from app.modules.library.background_tasks import apply_dj_fingerprint
    apply_dj_fingerprint(db, song)
    song.analysis_status = "completed"
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
        from app.modules.library.background_tasks import apply_stem_analysis
        apply_stem_analysis(song)
        from app.modules.library.background_tasks import apply_dj_fingerprint
        apply_dj_fingerprint(db, song)
        db.commit()
        return APIResponse(data={"stems": stems, "stem_quality_score": song.stem_quality_score})

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
    from app.modules.library.background_tasks import apply_stem_analysis
    apply_stem_analysis(song)
    from app.modules.library.background_tasks import apply_dj_fingerprint
    apply_dj_fingerprint(db, song)
    db.commit()
    return APIResponse(data={"stems": stems, "stem_quality_score": song.stem_quality_score})
