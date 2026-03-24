from __future__ import annotations

import math

from sqlalchemy import String, cast, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.track import Track
from app.models.user_radar import UserRadar
from app.playlist_engine import PlaylistEngine

settings = get_settings()


def get_simple_recommendations(db: Session, top_k: int):
    stmt = select(Track).limit(top_k)
    tracks = db.scalars(stmt).all()

    return [
        {
            "song_id": track.id,
            "title": track.title,
            "artist": str((track.genre_tags or {}).get("artist", "unknown")),
            "score": 1.0,
        }
        for track in tracks
    ]


def generate_practice_list(db: Session, user_id: int, target_duration: int) -> list[Track]:
    _ = user_id  # 预留：后续可引入用户偏好起始曲选择
    tracks = db.scalars(select(Track).order_by(Track.energy.desc())).all()
    return PlaylistEngine.build_practice_list(tracks, target_duration)


def radar_to_embedding(style_scores: dict[str, float], dim: int = 128) -> list[float]:
    vec = [0.0] * dim
    for style, score in style_scores.items():
        idx = hash(style.lower()) % dim
        vec[idx] += float(score)

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]

    return vec


def recommend_cypher_track(db: Session, user_id: int):
    radar = db.get(UserRadar, user_id)
    if not radar:
        return None

    query_vector = radar_to_embedding(radar.style_scores or {}, settings.vector_dim)
    distance = Track.embedding.cosine_distance(query_vector).label("distance")

    stmt = (
        select(Track, distance)
        .where(cast(Track.genre_tags, String).ilike("%cypher%"))
        .order_by(distance)
        .limit(1)
    )

    row = db.execute(stmt).first()
    if not row:
        return None

    track, dist = row
    score = max(0.0, 1.0 - float(dist))
    return track, score
