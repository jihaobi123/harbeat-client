from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Dance AI Recommender API"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "dance_app"
    postgres_user: str = "ai_user"
    postgres_password: str = "ai_password"

    redis_host: str = "localhost"
    redis_port: int = 6379

    vector_dim: int = Field(default=128, ge=1)

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
