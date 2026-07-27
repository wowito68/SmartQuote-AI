from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    project_name: str = Field(default="SmartQuote AI")
    version: str = Field(default="0.5.0")
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

    openai_api_key: SecretStr | None = Field(default=None)
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_timeout_seconds: float = Field(default=90.0, gt=0, le=600)
    ai_model: str = Field(default="gpt-5-mini")
    ai_prompt_version: str = Field(default="1.0.0")
    ai_temperature: float = Field(default=0.0, ge=0, le=2)
    ai_input_cost_per_million_tokens: float = Field(default=0.0, ge=0)
    ai_output_cost_per_million_tokens: float = Field(default=0.0, ge=0)

    supplier_directory_path: Path = Field(
        default=Path("app/supplier_sources/default_directory.json")
    )
    supplier_search_country: str | None = Field(default="MX")
    supplier_search_max_results_per_product: int = Field(default=10, ge=1, le=100)
    supplier_matching_algorithm_version: str = Field(default="1.0.0")

    company_name: str = Field(default="SmartQuote AI")
    company_contact_name: str = Field(default="Equipo de Compras")
    company_email: str = Field(default="procurement@smartquote.local")
    company_phone: str | None = Field(default=None)
    rfq_template_name: str = Field(default="supplier_rfq")
    rfq_template_version: str = Field(default="1.0.0")
    max_email_attachment_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    smtp_host: str = Field(default="localhost")
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str | None = Field(default=None)
    smtp_password: SecretStr | None = Field(default=None)
    smtp_use_tls: bool = Field(default=False)
    smtp_use_ssl: bool = Field(default=False)
    smtp_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    smtp_sender_email: str = Field(default="procurement@smartquote.local")
    smtp_sender_name: str = Field(default="SmartQuote AI Compras")
    smtp_message_id_domain: str = Field(default="smartquote.local")

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_prefix="SMARTQUOTE_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
