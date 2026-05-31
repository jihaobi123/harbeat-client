from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    edge_token: str = ""
    rk_id: str = "rk-001"
    jetson_base_url: str = "http://100.87.142.21:8000"
    jwt_token: str = ""
    harbeat_rk_token: str = ""
    sync_worker_url: str = "http://127.0.0.1:9100"
    audio_socket: str = "/tmp/cypher-audio.sock"
    cypher_home: Path = Path.home() / "cypher"
    event_flush_interval_sec: float = 5.0
    event_flush_batch_size: int = 50

    # Network URLs for client connection
    tailscale_url: str = ""
    gateway_url: str = "http://8.136.120.255"

    rest_host: str = "0.0.0.0"
    rest_port: int = 9000
    ws_host: str = "0.0.0.0"
    ws_port: int = 9001

    @property
    def plans_dir(self) -> Path:
        return self.cypher_home / "plans"

    @property
    def current_plan_path(self) -> Path:
        return self.plans_dir / "current.json"

    @property
    def logs_dir(self) -> Path:
        return self.cypher_home / "logs"

    @property
    def session_id_path(self) -> Path:
        return self.logs_dir / "session-id.txt"

    @property
    def event_buffer_path(self) -> Path:
        return self.logs_dir / "events-buffer.jsonl"


settings = Settings()
