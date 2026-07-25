from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    project_name: str = Field(default="SmartQuote AI")
    version: str = Field(default="0.1.0")
    environment: Environment = Field(default="local")
    api_v1_prefix: str = Field(default="/api/v1")
    database_url: SecretStr
    storage_root: Path = Field(default=Path("storage/private"))
    max_document_size_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    max_documents_per_upload: int = Field(default=10, gt=0, le=50)

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_prefix="SMARTQUOTE_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
