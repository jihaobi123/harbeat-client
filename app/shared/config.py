from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Street Dance MVP API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    upload_dir: str = "./data/music-files"
    annotation_dir: str = "./data/annotations"
    presence_dataset_version: str = "bar-presence-pilot-1.0.0"
    bar_annotation_dir: str = "./data/bar-annotations"
    bar_annotation_pilot_manifest: str = "./config/public-annotation-pilot.json"
    songformer_section_dir: str = "./data/songformer-sections"
    songformer_work_dir: str = "./data/songformer-cache"
    songformer_command: str = ""
    songformer_timeout_sec: int = 1800
    songformer_enabled: bool = False
    instrument_analysis_enabled: bool = False
    instrument_analysis_dir: str = "./data/instrument-analysis"
    instrument_analysis_work_dir: str = "./data/instrument-analysis-cache"
    instrument_analysis_command: str = ""
    instrument_analysis_timeout_sec: int = 1800
    edm_structure_enabled: bool = False
    edm_structure_dir: str = "./data/edm-structure"
    edm_structure_work_dir: str = "./data/edm-structure-cache"
    edm_structure_command: str = ""
    edm_structure_timeout_sec: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
