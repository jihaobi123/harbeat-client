from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.library.models import LibrarySong
from app.modules.music.schemas import SongProcessRequest
from app.modules.music.service import process_song_for_styles
from app.modules.playlists.models import Playlist, PlaylistSong, Song, SongTag
from app.modules.playlists.schemas import (
    DJMixRequest,
    DJMixResult,
    PlaylistDetailData,
    PlaylistImportRequest,
    PlaylistListData,
    PlaylistSongData,
    PlaylistSummaryData,
    SegmentInfo,
    StyleMixRequest,
    StyleMixResult,
    TransitionData,
)
from app.modules.users.service import get_user_or_404


def import_playlist(db: Session, payload: PlaylistImportRequest) -> tuple[Playlist, int]:
    get_user_or_404(db, payload.user_id)

    playlist = Playlist(
        user_id=payload.user_id,
        playlist_name=payload.playlist_name,
        source_type=payload.source_type,
    )
    db.add(playlist)
    db.flush()

    pending_analysis_count = 0

    for index, item in enumerate(payload.songs):
        song = db.query(Song).filter(Song.title == item.title, Song.artist == item.artist).first()
        if not song:
            song = Song(
                title=item.title,
                artist=item.artist,
                audio_url=str(item.audio_url) if item.audio_url else None,
                duration=item.duration,
            )
            db.add(song)
            db.flush()
            if item.bpm is not None or item.tags:
                db.add(SongTag(song_id=song.id, bpm=item.bpm, style=",".join(item.tags) if item.tags else None))
        elif (item.bpm is not None or item.tags) and song.tags is None:
            db.add(SongTag(song_id=song.id, bpm=item.bpm, style=",".join(item.tags) if item.tags else None))
        elif song.tags is not None:
            if item.bpm is not None:
                song.tags.bpm = item.bpm
            if item.tags:
                song.tags.style = ",".join(item.tags)

        relation = PlaylistSong(playlist_id=playlist.id, song_id=song.id, order_index=index)
        db.add(relation)

        if song.tags is None:
            pending_analysis_count += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"failed to import playlist: {exc}",
        ) from exc

    db.refresh(playlist)
    return playlist, pending_analysis_count


def list_playlists(db: Session, user_id: int) -> PlaylistListData:
    get_user_or_404(db, user_id)
    playlists = db.query(Playlist).filter(Playlist.user_id == user_id).order_by(Playlist.created_at.desc()).all()
    return PlaylistListData(
        playlists=[
            PlaylistSummaryData(
                id=playlist.id,
                user_id=playlist.user_id,
                playlist_name=playlist.playlist_name,
                source_type=playlist.source_type,
                song_count=len(playlist.songs),
            )
            for playlist in playlists
        ]
    )


def get_playlist_detail(db: Session, playlist_id: int) -> PlaylistDetailData:
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")

    songs = (
        db.query(PlaylistSong)
        .filter(PlaylistSong.playlist_id == playlist_id)
        .order_by(PlaylistSong.order_index.asc())
        .all()
    )

    return PlaylistDetailData(
        id=playlist.id,
        user_id=playlist.user_id,
        playlist_name=playlist.playlist_name,
        source_type=playlist.source_type,
        songs=[
            PlaylistSongData(
                song_id=item.song.id,
                title=item.song.title,
                artist=item.song.artist,
                audio_url=item.song.audio_url,
                duration=item.song.duration,
                bpm=item.song.tags.bpm if item.song.tags else None,
                tags=[part for part in (item.song.tags.style or "").split(",") if part] if item.song.tags else [],
                order_index=item.order_index,
            )
            for item in songs
        ],
    )


def delete_playlist(db: Session, playlist_id: int) -> None:
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")
    db.delete(playlist)
    db.commit()


def update_playlist_song_tags(db: Session, playlist_id: int, song_id: int, tags: list[str]) -> None:
    relation = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == playlist_id, PlaylistSong.song_id == song_id).first()
    if not relation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist song not found")

    tag = relation.song.tags
    if tag is None:
        tag = SongTag(song_id=song_id)
        db.add(tag)
    tag.style = ",".join(tags) if tags else None
    db.commit()


def create_empty_playlist(db: Session, user_id: int, name: str) -> Playlist:
    playlist = Playlist(user_id=user_id, playlist_name=name, source_type="manual")
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return playlist


def add_library_songs_to_playlist(db: Session, playlist_id: int, user_id: int, library_song_ids: list[str]) -> int:
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")
    if playlist.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your playlist")

    max_order = (
        db.query(PlaylistSong.order_index)
        .filter(PlaylistSong.playlist_id == playlist_id)
        .order_by(PlaylistSong.order_index.desc())
        .first()
    )
    next_order = (max_order[0] + 1) if max_order else 0

    added = 0
    for lib_song_id in library_song_ids:
        lib_song = db.get(LibrarySong, lib_song_id)
        if not lib_song or lib_song.user_id != user_id:
            continue

        song = db.query(Song).filter(Song.title == lib_song.title, Song.artist == lib_song.artist).first()
        if not song:
            song = Song(title=lib_song.title, artist=lib_song.artist, duration=lib_song.duration)
            db.add(song)
            db.flush()

        if lib_song.song_id != song.id:
            lib_song.song_id = song.id

        existing = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == playlist_id, PlaylistSong.song_id == song.id).first()
        if existing:
            continue

        db.add(PlaylistSong(playlist_id=playlist_id, song_id=song.id, order_index=next_order))
        next_order += 1
        added += 1

    db.commit()
    return added


def generate_style_mix_playlist(db: Session, payload: StyleMixRequest) -> StyleMixResult:
    """
    练舞会话长歌单生成：
    1. 从服务器曲库按 style/bpm/energy 筛歌
    2. 累计到目标时长
    3. 对每首歌应用单曲风格处理，并返回模型选择信息
    """
    query = db.query(Song).join(SongTag).filter(SongTag.style.ilike(f"%{payload.style}%"))
    if payload.bpm is not None:
        # 允许少量偏差，适合练舞连续性
        query = query.filter(SongTag.bpm >= payload.bpm - 4, SongTag.bpm <= payload.bpm + 4)
    if payload.energy is not None:
        query = query.filter(SongTag.energy.ilike(f"%{payload.energy}%"))

    songs = query.order_by(SongTag.bpm.asc(), Song.created_at.desc()).all()

    # Fallback: if style filter returns too few results, include all songs with audio
    if len(songs) < 3:
        fallback = (
            db.query(Song)
            .filter(Song.audio_url.isnot(None), Song.duration.isnot(None))
            .order_by(Song.created_at.desc())
            .all()
        )
        seen = {s.id for s in songs}
        for s in fallback:
            if s.id not in seen:
                songs.append(s)

    selected: list[Song] = []
    total_seconds = 0
    target_seconds = max(payload.duration_minutes, 1) * 60

    for song in songs:
        if song.duration is None or song.duration <= 0:
            continue
        if not song.audio_url:
            continue
        selected.append(song)
        total_seconds += int(song.duration)
        if total_seconds >= target_seconds:
            break

    playlist_data = [
        PlaylistSongData(
            song_id=song.id,
            title=song.title,
            artist=song.artist,
            audio_url=song.audio_url,
            duration=song.duration,
            bpm=song.tags.bpm if song.tags else None,
            tags=[part for part in (song.tags.style or "").split(",") if part] if song.tags else [],
            order_index=index,
        )
        for index, song in enumerate(selected)
    ]

    processed_files: dict[int, str] = {}
    stem_files: dict[int, dict[str, str]] = {}
    meta: dict[int, dict[str, str]] = {}

    for song in selected:
        one_song_result = process_song_for_styles(
            db,
            song.id,
            SongProcessRequest(
                styles=[payload.style],
                bpm=payload.bpm,
                energy=payload.energy,
                quality_mode=payload.quality_mode,
            ),
        )
        processed_files[song.id] = one_song_result.processed_files.get(payload.style, "")
        style_meta = one_song_result.meta.get(payload.style)
        meta[song.id] = style_meta.selected_models if style_meta else {}

        # Collect stem file paths (drums/bass/vocals/other)
        main_path = processed_files[song.id]
        if main_path:
            import os
            base = main_path.rsplit(".", 1)[0]  # strip .wav
            song_stems: dict[str, str] = {}
            for stem_name in ("drums", "bass", "vocals", "other"):
                sp = f"{base}_{stem_name}.wav"
                if os.path.isfile(sp):
                    song_stems[stem_name] = sp
            if song_stems:
                stem_files[song.id] = song_stems

    return StyleMixResult(playlist=playlist_data, processed_files=processed_files, stem_files=stem_files, meta=meta)


def generate_dj_mix(db: Session, payload: DJMixRequest) -> DJMixResult:
    """
    DJ.studio-inspired Harmonize 排歌 + 专业过渡：
    1. 从曲库筛选歌曲（BPM ±5%，风格匹配）
    2. 特征提取（BPM/Key/Energy/Downbeat/Phrase）
    3. Harmonize 全局排歌 (Held-Karp DP 或 Greedy+2-opt)
    4. 每首歌完整播放，计算 mix-in/mix-out 点
    5. 生成 DJ.studio 风格过渡自动化 (smooth/power/bass_swap/echo_out/filter/cut/slam)
    """
    import os
    from app.modules.music.dj_sequencer import DJTrack, build_dj_set
    from app.modules.music.dj_transition import generate_transition_automation

    # ── Step 1: Query candidate songs ──
    query = db.query(Song).join(SongTag).filter(SongTag.style.ilike(f"%{payload.style}%"))
    if payload.bpm is not None:
        tolerance = max(4, int(payload.bpm * 0.05))
        query = query.filter(SongTag.bpm >= payload.bpm - tolerance, SongTag.bpm <= payload.bpm + tolerance)

    songs = query.order_by(SongTag.bpm.asc(), Song.created_at.desc()).all()

    if len(songs) < 3:
        fallback = (
            db.query(Song)
            .filter(Song.audio_url.isnot(None), Song.duration.isnot(None))
            .order_by(Song.created_at.desc())
            .all()
        )
        seen = {s.id for s in songs}
        for s in fallback:
            if s.id not in seen:
                songs.append(s)

    selected: list[Song] = []
    total_sec = 0
    target_sec = max(payload.duration_minutes, 1) * 60
    for song in songs:
        if not song.duration or song.duration <= 0 or not song.audio_url:
            continue
        selected.append(song)
        total_sec += int(song.duration)
        if total_sec >= target_sec:
            break

    if not selected:
        return DJMixResult()

    # ── Step 2: Build DJTrack objects with features from LibrarySong ──
    dj_tracks: list[DJTrack] = []
    for song in selected:
        lib_song = (
            db.query(LibrarySong)
            .filter(LibrarySong.song_id == song.id, LibrarySong.analysis_status == "completed")
            .first()
        )

        bpm = float(song.tags.bpm) if song.tags and song.tags.bpm else 120.0
        energy = 0.5
        camelot_key = ""
        downbeats: list[float] = []
        phrase_map: list[dict] = []
        beat_points: list[float] = []
        key_confidence = 0.0

        if lib_song:
            bpm = lib_song.bpm or bpm
            energy = lib_song.energy or energy
            camelot_key = lib_song.camelot_key or ""
            downbeats = lib_song.downbeats or []
            phrase_map = lib_song.phrase_map or []
            beat_points = lib_song.beat_points or []
            key_confidence = lib_song.key_confidence or 0.0

        dj_tracks.append(DJTrack(
            song_id=song.id, title=song.title, artist=song.artist,
            bpm=bpm, camelot_key=camelot_key, energy=energy,
            duration=song.duration or 0, key_confidence=key_confidence,
            downbeats=downbeats, phrase_map=phrase_map, beat_points=beat_points,
        ))

    # ── Step 3: Harmonize sequencing (global optimal ordering + mix points) ──
    ordered, plans = build_dj_set(
        dj_tracks,
        energy_profile=payload.energy_profile,
        harmonic_weight=payload.harmonic_weight,
        overlap_bars=payload.overlap_bars,
        start_song_id=payload.start_song_id,
    )

    # ── Step 4: Build segments + transition automation ──
    segments_map: dict[int, SegmentInfo] = {}
    transition_data: list[TransitionData] = []

    for plan in plans:
        # Segment for A: full song play range
        if plan.from_song_id not in segments_map:
            segments_map[plan.from_song_id] = SegmentInfo(
                start_sec=plan.a_play_start, end_sec=plan.a_play_end,
                bars=0, label="full",
            )
        # Segment for B: full song play range
        if plan.to_song_id not in segments_map:
            segments_map[plan.to_song_id] = SegmentInfo(
                start_sec=plan.b_play_start, end_sec=plan.b_play_end,
                bars=0, label="full",
            )

        auto = generate_transition_automation(
            overlap_sec=plan.overlap_sec,
            overlap_bars=plan.overlap_bars,
            bpm=next((t.bpm for t in ordered if t.song_id == plan.from_song_id), 120),
            style=payload.transition_style,
        )
        transition_data.append(TransitionData(
            from_song_id=plan.from_song_id,
            to_song_id=plan.to_song_id,
            score=plan.score,
            bpm_score=plan.bpm_score,
            key_score=plan.key_score,
            energy_score=plan.energy_score,
            a_play_start=plan.a_play_start,
            a_play_end=plan.a_play_end,
            b_play_start=plan.b_play_start,
            b_play_end=plan.b_play_end,
            overlap_bars=plan.overlap_bars,
            overlap_sec=plan.overlap_sec,
            mix_start_time=plan.mix_start_time,
            mix_duration_sec=plan.mix_duration_sec,
            mix_duration_bars=plan.mix_duration_bars,
            b_cue_time=plan.b_cue_time,
            bpm_shift=plan.bpm_shift,
            automation={
                "sample_rate": auto.sample_rate,
                "a_drums": auto.a_drums,
                "a_bass": auto.a_bass,
                "a_vocals": auto.a_vocals,
                "a_other": auto.a_other,
                "a_volume": auto.a_volume,
                "a_echo": auto.a_echo,
                "b_drums": auto.b_drums,
                "b_bass": auto.b_bass,
                "b_vocals": auto.b_vocals,
                "b_other": auto.b_other,
                "b_volume": auto.b_volume,
            },
        ))

    # Ensure all tracks have segments
    for track in ordered:
        if track.song_id not in segments_map:
            segments_map[track.song_id] = SegmentInfo(
                start_sec=0, end_sec=track.duration,
                bars=0, label="full",
            )

    # ── Step 5: Process audio + collect stems ──
    ordered_songs = {t.song_id: t for t in ordered}
    song_id_order = [t.song_id for t in ordered]
    processed_files: dict[int, str] = {}
    stem_files: dict[int, dict[str, str]] = {}

    for song in selected:
        if song.id not in ordered_songs:
            continue
        one_result = process_song_for_styles(
            db, song.id,
            SongProcessRequest(
                styles=[payload.style],
                bpm=payload.bpm,
                energy=payload.energy,
                quality_mode=payload.quality_mode,
            ),
        )
        processed_files[song.id] = one_result.processed_files.get(payload.style, "")
        main_path = processed_files[song.id]
        if main_path:
            base = main_path.rsplit(".", 1)[0]
            song_stems: dict[str, str] = {}
            for stem_name in ("drums", "bass", "vocals", "other"):
                sp = f"{base}_{stem_name}.wav"
                if os.path.isfile(sp):
                    song_stems[stem_name] = sp
            if song_stems:
                stem_files[song.id] = song_stems

    # Build ordered playlist
    playlist_data: list[PlaylistSongData] = []
    for i, sid in enumerate(song_id_order):
        song = next((s for s in selected if s.id == sid), None)
        if not song:
            continue
        playlist_data.append(PlaylistSongData(
            song_id=song.id, title=song.title, artist=song.artist,
            audio_url=song.audio_url, duration=song.duration,
            bpm=song.tags.bpm if song.tags else None,
            tags=[p for p in (song.tags.style or "").split(",") if p] if song.tags else [],
            order_index=i,
        ))

    total_dur = sum(
        (segments_map.get(s.id, SegmentInfo(start_sec=0, end_sec=s.duration or 0, bars=0)).end_sec -
         segments_map.get(s.id, SegmentInfo(start_sec=0, end_sec=s.duration or 0, bars=0)).start_sec)
        for s in selected if s.id in ordered_songs
    )
    avg_score = sum(t.score for t in transition_data) / max(len(transition_data), 1)

    return DJMixResult(
        playlist=playlist_data,
        processed_files=processed_files,
        stem_files=stem_files,
        segments=segments_map,
        transitions=transition_data,
        energy_profile=payload.energy_profile,
        harmonic_weight=payload.harmonic_weight,
        total_duration_sec=round(total_dur, 1),
        avg_score=round(avg_score, 1),
    )
