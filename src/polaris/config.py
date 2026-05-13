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

    # Cloudinary (for video uploads)
    cloudinary_cloud_name: Optional[str] = Field(default=None, description="Cloudinary cloud name")
    cloudinary_api_key: Optional[str] = Field(default=None, description="Cloudinary API key")
    cloudinary_api_secret: Optional[str] = Field(default=None, description="Cloudinary API secret")

    # Email notifications (comma-separated for multiple recipients)
    notification_email: Optional[str] = Field(
        default=None,
        description="Email address(es) to send lead notifications to. Separate multiple with commas.",
    )
    smtp_host: str = Field(default="smtp.gmail.com", description="SMTP host")
    smtp_port: int = Field(default=587, description="SMTP port")
    smtp_username: Optional[str] = Field(default=None, description="SMTP username (your Gmail address)")
    smtp_password: Optional[str] = Field(default=None, description="SMTP password (Gmail App Password)")

    # Yelp API (prospect discovery)
    yelp_api_key: Optional[str] = Field(
        default=None,
        description="Yelp Fusion API key for prospect discovery",
    )

    # Google Places API (prospect discovery fallback)
    google_places_api_key: Optional[str] = Field(
        default=None,
        description="Google Places API key for prospect discovery",
    )

    # Google Sheets (outreach tracking)
    google_sheets_client_secrets_file: Optional[str] = Field(
        default=None,
        description="Path to Google OAuth client secrets JSON file (Desktop app credentials)",
    )
    google_sheets_token_file: str = Field(
        default="google_sheets_token.json",
        description="Path to store the OAuth token after first authorization",
    )
    google_sheets_spreadsheet_id: Optional[str] = Field(
        default=None,
        description="Google Sheets spreadsheet ID (from the sheet URL)",
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

    @property
    def is_cloudinary_configured(self) -> bool:
        """Check if Cloudinary credentials are configured."""
        return bool(self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret)

    @property
    def notification_emails(self) -> list[str]:
        """Return list of notification email addresses."""
        if not self.notification_email:
            return []
        return [e.strip() for e in self.notification_email.split(",") if e.strip()]

    @property
    def is_sheets_configured(self) -> bool:
        """Check if Google Sheets integration is configured."""
        return bool(self.google_sheets_client_secrets_file and self.google_sheets_spreadsheet_id)

    @property
    def is_email_configured(self) -> bool:
        """Check if email notifications are configured."""
        return bool(self.notification_email and self.smtp_username and self.smtp_password)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
