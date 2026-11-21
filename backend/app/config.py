"""CrowdVision Main Backend Configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "CrowdVision Platform API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    port: Optional[int] = None
    data_dir: Optional[str] = None
    app_log_level: str = "INFO"

    jwt_secret_key: str = "CHANGE_ME_CROWDVISION_JWT_SECRET_2026"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    allowed_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    database_url: str = "sqlite+aiosqlite:///./crowdvision_main.db"
    db_echo: bool = False
    data_retention_days: int = 30

    upload_dir: str = "uploads"
    max_upload_size_mb: int = 500
    max_video_duration_seconds: float = 14400.0  # 4 hours max
    max_video_dimension: int = 4096              # 4K max
    max_image_size_mb: int = 25                  # 25 MB max
    sample_fps: float = 2.0
    inference_width: int = 640
    inference_confidence: float = 0.35
    yolo_model_path: str = "models/yolov8n.onnx"

    forecast_horizons_seconds: str = "60,180,300"
    min_history_for_prediction: int = 5

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "auto"
    llm_timeout_seconds: float = 30.0
    llm_enabled: bool = True

    ai_agent_base_url: str = "http://localhost:8001"
    ai_agent_url: str = "http://localhost:8001"
    ai_agent_api_key: str = "CHANGE_ME_TO_A_RANDOM_SECRET_KEY"
    ai_agent_timeout_seconds: float = 5.0
    ai_agent_enabled: bool = True

    @property
    def effective_port(self) -> int:
        if self.port is not None:
            return self.port
        return self.app_port

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def forecast_horizons_list(self) -> list[int]:
        return [int(x.strip()) for x in self.forecast_horizons_seconds.split(",") if x.strip()]

    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def effective_storage_root(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir).resolve()
        return self.base_dir

    @property
    def videos_dir(self) -> Path:
        p = self.effective_storage_root / self.upload_dir / "videos"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def floorplans_dir(self) -> Path:
        p = self.effective_storage_root / self.upload_dir / "floorplans"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def processed_dir(self) -> Path:
        p = self.effective_storage_root / self.upload_dir / "processed"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def images_dir(self) -> Path:
        p = self.effective_storage_root / self.upload_dir / "images"
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
