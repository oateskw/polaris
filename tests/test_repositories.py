"""Tests for repository classes."""

from datetime import datetime, timedelta, timezone

import pytest

from polaris.models.account import InstagramAccount
from polaris.models.content import Content, ContentStatus
from polaris.models.schedule import ScheduleStatus
from polaris.repositories import (
    AccountRepository,
    AnalyticsRepository,
    ContentRepository,
    ScheduleRepository,
)


class TestAccountRepository:
    """Tests for AccountRepository."""

    def test_create_and_get(self, session, sample_account_data):
        """Test creating and retrieving an account."""
        repo = AccountRepository(session)

        account = repo.create(**sample_account_data)
        repo.commit()

        retrieved = repo.get(account.id)
        assert retrieved is not None
        assert retrieved.username == sample_account_data["username"]

    def test_get_by_instagram_id(self, session, sample_account_data):
        """Test getting account by Instagram ID."""
        repo = AccountRepository(session)

        account = repo.create(**sample_account_data)
        repo.commit()

        retrieved = repo.get_by_instagram_id(sample_account_data["instagram_user_id"])
        assert retrieved is not None
        assert retrieved.id == account.id

    def test_get_by_username(self, session, sample_account_data):
        """Test getting account by username."""
        repo = AccountRepository(session)

        account = repo.create(**sample_account_data)
        repo.commit()

        retrieved = repo.get_by_username(sample_account_data["username"])
        assert retrieved is not None
        assert retrieved.id == account.id

    def test_get_active_accounts(self, session, sample_account_data):
        """Test getting active accounts."""
        repo = AccountRepository(session)

        # Create active account
        repo.create(**sample_account_data)

        # Create inactive account
        inactive_data = sample_account_data.copy()
        inactive_data["instagram_user_id"] = "98765432109"
        inactive_data["username"] = "inactive_account"
        inactive_data["is_active"] = False
        repo.create(**inactive_data)
        repo.commit()

        active_accounts = repo.get_active_accounts()
        assert len(active_accounts) == 1
        assert active_accounts[0].is_active is True

    def test_deactivate_account(self, session, sample_account_data):
        """Test deactivating an account."""
        repo = AccountRepository(session)

        account = repo.create(**sample_account_data)
        repo.commit()

        repo.deactivate(account.id)
        repo.commit()

        retrieved = repo.get(account.id)
        assert retrieved.is_active is False

    def test_update_token(self, session, sample_account_data):
        """Test updating account token."""
        repo = AccountRepository(session)

        account = repo.create(**sample_account_data)
        repo.commit()

        new_token = "new_access_token_456"
        new_expires = datetime.now(timezone.utc) + timedelta(days=60)

        repo.update_token(account.id, new_token, new_expires)
        repo.commit()

        retrieved = repo.get(account.id)
        assert retrieved.access_token == new_token


class TestContentRepository:
    """Tests for ContentRepository."""

    def test_create_content(self, session, sample_account_data, sample_content_data):
        """Test creating content."""
        account_repo = AccountRepository(session)
        content_repo = ContentRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        content = content_repo.create_content(
            account_id=account.id,
            **sample_content_data,
        )
        content_repo.commit()

        assert content.id is not None
        assert content.status == ContentStatus.DRAFT

    def test_get_drafts(self, session, sample_account_data, sample_content_data):
        """Test getting draft content."""
        account_repo = AccountRepository(session)
        content_repo = ContentRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        # Create draft
        content_repo.create_content(account_id=account.id, **sample_content_data)

        # Create ready content
        ready_data = sample_content_data.copy()
        content = content_repo.create_content(account_id=account.id, **ready_data)
        content_repo.mark_ready(content.id)
        content_repo.commit()

        drafts = content_repo.get_drafts()
        assert len(drafts) == 1
        assert drafts[0].status == ContentStatus.DRAFT

    def test_mark_ready(self, session, sample_account_data, sample_content_data):
        """Test marking content as ready."""
        account_repo = AccountRepository(session)
        content_repo = ContentRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        content = content_repo.create_content(account_id=account.id, **sample_content_data)
        content_repo.mark_ready(content.id)
        content_repo.commit()

        retrieved = content_repo.get(content.id)
        assert retrieved.status == ContentStatus.READY

    def test_mark_published(self, session, sample_account_data, sample_content_data):
        """Test marking content as published."""
        account_repo = AccountRepository(session)
        content_repo = ContentRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        content = content_repo.create_content(account_id=account.id, **sample_content_data)
        content_repo.mark_published(content.id, "ig_media_12345")
        content_repo.commit()

        retrieved = content_repo.get(content.id)
        assert retrieved.status == ContentStatus.PUBLISHED
        assert retrieved.instagram_media_id == "ig_media_12345"


class TestScheduleRepository:
    """Tests for ScheduleRepository."""

    def test_create_scheduled_post(self, session, sample_account_data, sample_content_data):
        """Test creating a scheduled post."""
        account_repo = AccountRepository(session)
        content_repo = ContentRepository(session)
        schedule_repo = ScheduleRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        content = content_repo.create_content(account_id=account.id, **sample_content_data)
        session.flush()

        scheduled_time = datetime.now(timezone.utc) + timedelta(hours=1)
        scheduled = schedule_repo.create_scheduled_post(
            account_id=account.id,
            content_id=content.id,
            scheduled_time=scheduled_time,
        )
        schedule_repo.commit()

        assert scheduled.id is not None
        assert scheduled.status == ScheduleStatus.PENDING

    def test_get_pending(self, session, sample_account_data, sample_content_data):
        """Test getting pending scheduled posts."""
        account_repo = AccountRepository(session)
        content_repo = ContentRepository(session)
        schedule_repo = ScheduleRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        content = content_repo.create_content(account_id=account.id, **sample_content_data)
        session.flush()

        # Create pending post
        schedule_repo.create_scheduled_post(
            account_id=account.id,
            content_id=content.id,
            scheduled_time=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        schedule_repo.commit()

        pending = schedule_repo.get_pending()
        assert len(pending) == 1

    def test_get_upcoming(self, session, sample_account_data, sample_content_data):
        """Test getting upcoming posts within time window."""
        account_repo = AccountRepository(session)
        content_repo = ContentRepository(session)
        schedule_repo = ScheduleRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        content = content_repo.create_content(account_id=account.id, **sample_content_data)
        session.flush()

        # Create post in next 24 hours
        schedule_repo.create_scheduled_post(
            account_id=account.id,
            content_id=content.id,
            scheduled_time=datetime.now(timezone.utc) + timedelta(hours=12),
        )

        # Create post outside window
        schedule_repo.create_scheduled_post(
            account_id=account.id,
            content_id=content.id,
            scheduled_time=datetime.now(timezone.utc) + timedelta(hours=48),
        )
        schedule_repo.commit()

        upcoming = schedule_repo.get_upcoming(hours=24)
        assert len(upcoming) == 1

    def test_mark_cancelled(self, session, sample_account_data, sample_content_data):
        """Test cancelling a scheduled post."""
        account_repo = AccountRepository(session)
        content_repo = ContentRepository(session)
        schedule_repo = ScheduleRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        content = content_repo.create_content(account_id=account.id, **sample_content_data)
        session.flush()

        scheduled = schedule_repo.create_scheduled_post(
            account_id=account.id,
            content_id=content.id,
            scheduled_time=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        schedule_repo.mark_cancelled(scheduled.id)
        schedule_repo.commit()

        retrieved = schedule_repo.get(scheduled.id)
        assert retrieved.status == ScheduleStatus.CANCELLED


class TestAnalyticsRepository:
    """Tests for AnalyticsRepository."""

    def test_record_metric(self, session, sample_account_data):
        """Test recording an engagement metric."""
        account_repo = AccountRepository(session)
        analytics_repo = AnalyticsRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        metric = analytics_repo.record_metric(
            account_id=account.id,
            instagram_media_id="media_123",
            recorded_at=datetime.now(timezone.utc),
            likes=100,
            comments=20,
        )
        analytics_repo.commit()

        assert metric.id is not None
        assert metric.likes == 100

    def test_get_account_totals(self, session, sample_account_data):
        """Test getting account totals."""
        account_repo = AccountRepository(session)
        analytics_repo = AnalyticsRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        # Record multiple metrics
        for i in range(3):
            analytics_repo.record_metric(
                account_id=account.id,
                instagram_media_id=f"media_{i}",
                recorded_at=datetime.now(timezone.utc),
                likes=100,
                comments=20,
                impressions=1000,
                reach=800,
            )
        analytics_repo.commit()

        totals = analytics_repo.get_account_totals(account.id)
        assert totals["total_likes"] == 300
        assert totals["total_comments"] == 60
        assert totals["post_count"] == 3

    def test_get_average_engagement(self, session, sample_account_data):
        """Test getting average engagement."""
        account_repo = AccountRepository(session)
        analytics_repo = AnalyticsRepository(session)

        account = account_repo.create(**sample_account_data)
        session.flush()

        # Record metrics
        for i in range(2):
            analytics_repo.record_metric(
                account_id=account.id,
                instagram_media_id=f"media_{i}",
                recorded_at=datetime.now(timezone.utc),
                likes=100 + i * 50,  # 100, 150
                comments=20,
            )
        analytics_repo.commit()

        averages = analytics_repo.get_average_engagement(account.id)
        assert averages["avg_likes"] == 125.0  # (100 + 150) / 2
        assert averages["avg_comments"] == 20.0
