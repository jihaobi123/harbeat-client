import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.library.schemas import (
    LibrarySongCreateRequest,
    LibrarySongData,
    LibrarySongListData,
    LibrarySongSummaryData,
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


class RefreshStyleEvidenceRequest(BaseModel):
    force: bool = False


class RefreshHighFrequencyStylesRequest(BaseModel):
    refresh_features: bool = False


class NormalizeSongRequest(BaseModel):
    target_lufs: float = -14.0


def _get_owned_song(db: Session, song_id: str, user_id: int):
    """Load a library song and enforce ownership."""
    from app.modules.library.models import LibrarySong

    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    if song.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your song")
    return song


def _waveform_from_energy_curve(song, points: int) -> dict:
    """Build approximate waveform peaks from stored energy analysis."""
    curve = getattr(song, "energy_curve", None) or []
    if not curve:
        return {}
    raw = [float(item.get("relative_energy", item.get("energy", 0.0)) or 0.0) for item in curve]
    if not raw:
        return {}
    if len(raw) == points:
        peaks = raw
    else:
        import numpy as np

        x_old = np.linspace(0.0, 1.0, len(raw))
        x_new = np.linspace(0.0, 1.0, points)
        peaks = [float(v) for v in np.interp(x_new, x_old, raw)]
    return {
        "song_id": song.id,
        "points": points,
        "duration": float(getattr(song, "duration", 0.0) or 0.0),
        "source": "energy_curve",
        "peaks": [round(max(0.0, min(1.0, p)), 4) for p in peaks],
    }


@router.get("/songs", response_model=APIResponse[LibrarySongListData])
def list_library_songs_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    songs = list_library_songs(db, current_user.id)
    return APIResponse(data=LibrarySongListData(songs=[LibrarySongSummaryData.model_validate(song) for song in songs]))


@router.get("/songs/search", response_model=APIResponse[LibrarySongListData])
def search_library_songs_endpoint(
    q: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    songs = search_library_songs(db, current_user.id, q)
    return APIResponse(data=LibrarySongListData(songs=[LibrarySongSummaryData.model_validate(song) for song in songs]))


@router.get("/songs/{song_id}", response_model=APIResponse[LibrarySongData])
def get_library_song_endpoint(
    song_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    song = _get_owned_song(db, song_id, current_user.id)
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.get("/songs/{song_id}/waveform", response_model=APIResponse[dict])
def get_song_waveform_endpoint(
    song_id: str,
    points: int = 1000,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return compact waveform peaks for Spotify Mix visualization."""
    song = _get_owned_song(db, song_id, current_user.id)
    points = max(64, min(4000, int(points or 1000)))
    cached = _waveform_from_energy_curve(song, points)
    if cached:
        return APIResponse(data=cached)
    if not song.source_path or not os.path.isfile(song.source_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio file not found on disk")

    try:
        import librosa
        import numpy as np

        audio, sr = librosa.load(song.source_path, sr=None, mono=True)
        if len(audio) == 0:
            peaks = [0.0] * points
        else:
            frame = max(1, int(np.ceil(len(audio) / points)))
            padded_len = frame * points
            padded = np.pad(audio, (0, padded_len - len(audio)))
            blocks = padded.reshape(points, frame)
            peaks = np.max(np.abs(blocks), axis=1)
            peak_max = float(np.max(peaks)) or 1.0
            peaks = peaks / peak_max
        return APIResponse(data={
            "song_id": song.id,
            "points": points,
            "duration": round(float(len(audio)) / float(sr), 3) if sr else song.duration,
            "source": "audio",
            "peaks": [round(float(v), 4) for v in peaks],
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"waveform generation failed: {exc}") from exc


@router.post("/songs/{song_id}/normalize", response_model=APIResponse[dict])
def normalize_song_loudness_endpoint(
    song_id: str,
    payload: NormalizeSongRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Analyze a song and store replay-gain metadata for target LUFS playback."""
    song = _get_owned_song(db, song_id, current_user.id)
    if not song.source_path or not os.path.isfile(song.source_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio file not found on disk")
    try:
        import librosa

        from app.modules.library.loudness import loudness_profile

        audio, sr = librosa.load(song.source_path, sr=None, mono=True)
        profile = loudness_profile(audio, int(sr), target_lufs=payload.target_lufs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"loudness normalization failed: {exc}") from exc
    song.loudness_profile = {**(song.loudness_profile or {}), **profile}
    db.commit()
    db.refresh(song)
    return APIResponse(data={"song_id": song.id, "loudness_profile": song.loudness_profile})


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
    song.beat_confidence = result.get("beat_confidence")
    song.beat_confidence_details = result.get("beat_confidence_details", {})
    song.beat_grid_offset = result.get("beat_grid_offset")
    song.beat_grid_interval = result.get("beat_grid_interval")
    song.beat_engines_used = result.get("beat_engines_used", [])
    song.beat_needs_review = int(result.get("beat_needs_review", False))
    song.energy_curve = result.get("energy_curve", [])
    song.loudness_profile = result.get("loudness_profile", {})
    song.time_signature = result.get("time_signature", {})
    groove = result.get("groove", {})
    song.groove_score = groove.get("score") if groove else None
    song.groove_profile = groove if groove else {}
    song.danceability_score = result.get("danceability_score")
    song.dancefloor_profile = result.get("dancefloor_profile", {})
    song.dj_hot_cues = result.get("dj_hot_cues", [])
    song.transition_windows = result.get("transition_windows", [])
    song.transition_recommendations = result.get("transition_recommendations", [])
    song.downbeats = result.get("downbeats", [])
    song.phrase_map = result.get("phrase_map", [])
    song.key_confidence = result.get("key_confidence")
    song.key_profile = result.get("key_profile", {})
    # Add IDs to cue points for frontend
    raw_cues = result.get("cue_points", [])
    song.cue_points = [
        {"id": f"cue-{song_id}-{i}", "time": c["time"], "label": c["label"], "color": c["color"]}
        for i, c in enumerate(raw_cues)
    ]
    from app.modules.library.background_tasks import _apply_genre_classification, apply_dj_fingerprint
    from app.modules.library.external_metadata import run_enrich_song_external_metadata
    apply_dj_fingerprint(db, song)
    _apply_genre_classification(db, song)
    run_enrich_song_external_metadata(db, song, force=False)
    song.analysis_status = "completed"
    db.commit()
    db.refresh(song)
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.post("/songs/{song_id}/refresh-style-evidence", response_model=APIResponse[LibrarySongData])
def refresh_style_evidence_endpoint(
    song_id: str,
    payload: RefreshStyleEvidenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.modules.library.external_metadata import run_enrich_song_external_metadata
    from app.modules.library.models import LibrarySong

    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    if song.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your song")
    try:
        run_enrich_song_external_metadata(db, song, force=payload.force)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"style evidence refresh failed: {e}",
        )
    db.refresh(song)
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.get("/songs/{song_id}/high-frequency-styles", response_model=APIResponse[dict])
def get_high_frequency_styles_endpoint(
    song_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return feature evidence and explainable 21-style ranking separately."""
    song = _get_owned_song(db, song_id, current_user.id)
    music_features = dict(song.music_features or {})
    return APIResponse(data={
        "song_id": song.id,
        "pre_style_features": music_features.get("pre_style_features", {}),
        "style_analysis": music_features.get("high_frequency_styles", {}),
    })


@router.post("/songs/{song_id}/refresh-high-frequency-styles", response_model=APIResponse[dict])
def refresh_high_frequency_styles_endpoint(
    song_id: str,
    payload: RefreshHighFrequencyStylesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-score stored evidence, optionally rebuilding stem-based features."""
    song = _get_owned_song(db, song_id, current_user.id)
    try:
        from app.modules.library.background_tasks import (
            apply_high_frequency_style_analysis,
            apply_stem_analysis,
        )

        if payload.refresh_features:
            if not song.stems:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="separated stems are required to refresh features",
                )
            apply_stem_analysis(song)
            result = (song.music_features or {}).get("high_frequency_styles", {})
        else:
            result = apply_high_frequency_style_analysis(song)
        db.add(song)
        db.commit()
        db.refresh(song)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"high-frequency style refresh failed: {exc}",
        ) from exc
    return APIResponse(data={"song_id": song.id, "style_analysis": result})


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
