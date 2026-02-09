"""Pytest configuration and fixtures."""

import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from polaris.models.base import Base


@pytest.fixture
def engine():
    """Create a test database engine with fresh tables for each test."""
    # Use in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """Create a test database session."""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_account_data():
    """Sample Instagram account data with unique ID per test."""
    # Use UUID to ensure uniqueness across tests
    unique_id = str(uuid.uuid4())[:11]
    return {
        "instagram_user_id": unique_id,
        "username": f"polarisinnovations_{unique_id[:6]}",
        "name": "Polaris Innovations",
        "access_token": "test_access_token_123",
        "token_expires_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "followers_count": 1000,
        "following_count": 100,
        "media_count": 50,
        "is_active": True,
    }


@pytest.fixture
def sample_content_data():
    """Sample content data."""
    return {
        "caption": "Test caption for a new tech post about AI innovations.",
        "hashtags": "#tech #ai #innovation #polaris",
        "topic": "AI innovations",
        "ai_generated": True,
        "ai_model": "claude-sonnet-4-20250514",
    }


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock settings for tests."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
    monkeypatch.setenv("META_APP_ID", "test_app_id")
    monkeypatch.setenv("META_APP_SECRET", "test_app_secret")

    from polaris.config import Settings
    return Settings()
