"""Tests for configuration."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestSettings:
    """Tests for Settings class."""

    def test_default_settings(self, monkeypatch, tmp_path):
        """Test default settings values."""
        # Clear any existing env vars
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("META_APP_ID", raising=False)
        monkeypatch.delenv("META_APP_SECRET", raising=False)

        # Change to temp directory to avoid reading .env
        monkeypatch.chdir(tmp_path)

        # Clear lru_cache
        from polaris.config import get_settings
        get_settings.cache_clear()

        from polaris.config import Settings
        settings = Settings(_env_file=None)

        assert settings.database_url == "sqlite:///polaris.db"
        assert settings.anthropic_api_key is None
        assert settings.meta_app_id is None
        assert settings.log_level == "INFO"

    def test_settings_from_env(self, monkeypatch, tmp_path):
        """Test settings loaded from environment variables."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key_123")
        monkeypatch.setenv("META_APP_ID", "app_123")
        monkeypatch.setenv("META_APP_SECRET", "secret_456")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        # Change to temp directory to avoid reading .env
        monkeypatch.chdir(tmp_path)

        from polaris.config import get_settings
        get_settings.cache_clear()

        from polaris.config import Settings
        settings = Settings(_env_file=None)

        assert settings.database_url == "postgresql://localhost/test"
        assert settings.anthropic_api_key == "test_key_123"
        assert settings.meta_app_id == "app_123"
        assert settings.meta_app_secret == "secret_456"
        assert settings.log_level == "DEBUG"

    def test_is_instagram_configured(self, monkeypatch, tmp_path):
        """Test is_instagram_configured property."""
        # Change to temp directory to avoid reading .env
        monkeypatch.chdir(tmp_path)

        from polaris.config import Settings

        # Not configured
        monkeypatch.delenv("META_APP_ID", raising=False)
        monkeypatch.delenv("META_APP_SECRET", raising=False)
        settings = Settings(_env_file=None)
        assert settings.is_instagram_configured is False

        # Partially configured
        monkeypatch.setenv("META_APP_ID", "app_123")
        settings = Settings(_env_file=None)
        assert settings.is_instagram_configured is False

        # Fully configured
        monkeypatch.setenv("META_APP_SECRET", "secret_456")
        settings = Settings(_env_file=None)
        assert settings.is_instagram_configured is True

    def test_is_anthropic_configured(self, monkeypatch, tmp_path):
        """Test is_anthropic_configured property."""
        # Change to temp directory to avoid reading .env
        monkeypatch.chdir(tmp_path)

        from polaris.config import Settings

        # Not configured
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        settings = Settings(_env_file=None)
        assert settings.is_anthropic_configured is False

        # Configured
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
        settings = Settings(_env_file=None)
        assert settings.is_anthropic_configured is True

    def test_get_settings_cached(self, monkeypatch, tmp_path):
        """Test that get_settings returns cached instance."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")

        # Change to temp directory to avoid reading .env
        monkeypatch.chdir(tmp_path)

        from polaris.config import get_settings
        get_settings.cache_clear()

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2
