from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    project_name: str = Field(default="SmartQuote AI")
    version: str = Field(default="0.2.0")
    environment: Environment = Field(default="local")
    api_v1_prefix: str = Field(default="/api/v1")
    database_url: SecretStr
    storage_root: Path = Field(default=Path("storage/private"))
    max_document_size_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    max_documents_per_upload: int = Field(default=10, gt=0, le=50)

    celery_broker_url: SecretStr = Field(default=SecretStr("redis://redis:6379/0"))
    celery_result_backend: SecretStr = Field(default=SecretStr("redis://redis:6379/1"))
    celery_task_always_eager: bool = Field(default=False)
    pending_document_scan_seconds: int = Field(default=60, ge=10, le=3600)

    extraction_minimum_characters: int = Field(default=100, ge=0)
    extraction_maximum_empty_page_percentage: float = Field(default=60.0, ge=0, le=100)
    extraction_minimum_characters_per_page: float = Field(default=20.0, ge=0)

    quality_ready_minimum_characters: int = Field(default=200, ge=0)
    quality_ready_maximum_empty_page_percentage: float = Field(default=25.0, ge=0, le=100)
    quality_ready_minimum_density: float = Field(default=1.5, ge=0)
    quality_ocr_maximum_characters: int = Field(default=50, ge=0)
    quality_ocr_minimum_empty_page_percentage: float = Field(default=50.0, ge=0, le=100)
    quality_ocr_maximum_density: float = Field(default=0.5, ge=0)

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_prefix="SMARTQUOTE_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
