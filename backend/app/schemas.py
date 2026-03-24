from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    user_id: int
    top_k: int = 5


class RecommendItem(BaseModel):
    song_id: int
    title: str
    artist: str
    score: float


class RecommendResponse(BaseModel):
    user_id: int
    items: list[RecommendItem]


class GeneratePracticeListRequest(BaseModel):
    user_id: int
    target_duration: int = Field(..., ge=1)


class PracticeTrackItem(BaseModel):
    id: int
    title: str
    bpm: float
    camelot_key: str
    energy: float
    genre_tags: dict


class GeneratePracticeListResponse(BaseModel):
    user_id: int
    target_duration: int
    tracks: list[PracticeTrackItem]


class CypherRecommendationResponse(BaseModel):
    track_id: int
    title: str
    score: float
