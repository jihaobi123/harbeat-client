from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Street Dance MVP API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "postgresql+psycopg2://harbeat:harbeat@localhost:5432/rhythm_prism"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    upload_dir: str = "./data/music-files"
    annotation_dir: str = "./data/annotations"
    public_asset_base_url: str = ""
    enable_external_style_enrichment: bool = True
    external_style_cache_ttl_days: int = 30
    external_style_timeout_sec: float = 8.0
    external_style_max_concurrency: int = 3
    lastfm_api_key: str = ""
    discogs_user_token: str = ""
    musicbrainz_app_name: str = "HarBeat"
    musicbrainz_app_version: str = "1.0.0"
    musicbrainz_contact_email: str = ""
    style_score_weight_external: float = 0.50
    style_score_weight_local: float = 0.35
    style_score_weight_manual: float = 0.10
    style_score_weight_tunable: float = 0.05
    style_external_weight_discogs: float = 0.45
    style_external_weight_lastfm: float = 0.35
    style_external_weight_musicbrainz: float = 0.20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
