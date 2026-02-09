"""Configuration management using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(
        default="sqlite:///polaris.db",
        description="Database connection URL",
    )

    # Anthropic API
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude",
    )

    # Meta/Instagram API
    meta_app_id: Optional[str] = Field(
        default=None,
        description="Meta App ID",
    )
    meta_app_secret: Optional[str] = Field(
        default=None,
        description="Meta App Secret",
    )
    meta_redirect_uri: str = Field(
        default="http://localhost:8000/callback",
        description="OAuth redirect URI",
    )

    # Replicate API (for image generation)
    replicate_api_key: Optional[str] = Field(
        default=None,
        description="Replicate API key for image generation",
    )

    # Hugging Face API (for image generation - free tier)
    huggingface_api_key: Optional[str] = Field(
        default=None,
        description="Hugging Face API key for image generation",
    )

    # GitHub (for media uploads)
    github_repo: Optional[str] = Field(
        default=None,
        description="GitHub repo for media uploads (e.g., 'username/repo')",
    )
    github_branch: str = Field(
        default="main",
        description="GitHub branch for uploads",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    # Paths
    data_dir: Path = Field(
        default=Path.home() / ".polaris",
        description="Data directory for local storage",
    )

    @property
    def is_instagram_configured(self) -> bool:
        """Check if Instagram API credentials are configured."""
        return bool(self.meta_app_id and self.meta_app_secret)

    @property
    def is_anthropic_configured(self) -> bool:
        """Check if Anthropic API key is configured."""
        return bool(self.anthropic_api_key)

    @property
    def is_replicate_configured(self) -> bool:
        """Check if Replicate API key is configured."""
        return bool(self.replicate_api_key)

    @property
    def is_huggingface_configured(self) -> bool:
        """Check if Hugging Face API key is configured."""
        return bool(self.huggingface_api_key)

    @property
    def is_image_generation_configured(self) -> bool:
        """Check if any image generation API is configured."""
        return self.is_huggingface_configured or self.is_replicate_configured


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
