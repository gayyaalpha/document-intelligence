"""Application configuration loaded from environment variables / .env file."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Azure Document Intelligence
    azure_document_intelligence_endpoint: str = Field(
        ..., description="Azure Document Intelligence endpoint URL"
    )
    azure_document_intelligence_key: str = Field(
        ..., description="Azure Document Intelligence API key"
    )
    azure_di_model_id: str = Field(
        default="prebuilt-layout",
        description="Azure DI model to use (prebuilt-layout, prebuilt-invoice, etc.)",
    )

    # Extraction backend
    default_extractor: str = Field(
        default="azure",
        description="Default extraction backend: 'azure' or 'vision'",
    )

    # Paths
    input_dir: Path = Field(default=Path("inputs/"))
    output_dir: Path = Field(default=Path("outputs/"))


# Module-level singleton — import this everywhere
settings = Settings()  # type: ignore[call-arg]
