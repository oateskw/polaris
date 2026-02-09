"""Tests for SQLAlchemy models."""

from datetime import datetime, timedelta, timezone

import pytest

from polaris.models.account import InstagramAccount
from polaris.models.analytics import EngagementMetric
from polaris.models.content import Content, ContentStatus, ContentType
from polaris.models.schedule import ScheduledPost, ScheduleStatus


class TestInstagramAccount:
    """Tests for InstagramAccount model."""

    def test_create_account(self, session, sample_account_data):
        """Test creating an Instagram account."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        assert account.id is not None
        assert account.username == sample_account_data["username"]
        assert account.is_active is True

    def test_is_token_expired_not_expired(self, session, sample_account_data):
        """Test token expiration check when not expired."""
        sample_account_data["token_expires_at"] = datetime.now(timezone.utc) + timedelta(days=30)
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        assert account.is_token_expired is False

    def test_is_token_expired_expired(self, session, sample_account_data):
        """Test token expiration check when expired."""
        sample_account_data["token_expires_at"] = datetime.now(timezone.utc) - timedelta(days=1)
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        assert account.is_token_expired is True

    def test_repr(self, session, sample_account_data):
        """Test account string representation."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        assert "polarisinnovations" in repr(account)


class TestContent:
    """Tests for Content model."""

    def test_create_content(self, session, sample_account_data, sample_content_data):
        """Test creating content."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        content = Content(account_id=account.id, **sample_content_data)
        session.add(content)
        session.flush()

        assert content.id is not None
        assert content.status == ContentStatus.DRAFT
        assert content.ai_generated is True

    def test_full_caption_with_hashtags(self, session, sample_account_data, sample_content_data):
        """Test full caption includes hashtags."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        content = Content(account_id=account.id, **sample_content_data)
        session.add(content)
        session.flush()

        full_caption = content.full_caption
        assert sample_content_data["caption"] in full_caption
        assert sample_content_data["hashtags"] in full_caption

    def test_full_caption_without_hashtags(self, session, sample_account_data):
        """Test full caption without hashtags."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        content = Content(
            account_id=account.id,
            caption="Test caption",
            hashtags=None,
        )
        session.add(content)
        session.flush()

        assert content.full_caption == "Test caption"

    def test_content_media_type_default(self, session, sample_account_data):
        """Test default media type is IMAGE."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        content = Content(account_id=account.id, caption="Test")
        session.add(content)
        session.flush()

        assert content.media_type == ContentType.IMAGE


class TestScheduledPost:
    """Tests for ScheduledPost model."""

    def test_create_scheduled_post(self, session, sample_account_data, sample_content_data):
        """Test creating a scheduled post."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        content = Content(account_id=account.id, **sample_content_data)
        session.add(content)
        session.flush()

        scheduled_time = datetime.now(timezone.utc) + timedelta(hours=1)
        scheduled_post = ScheduledPost(
            account_id=account.id,
            content_id=content.id,
            scheduled_time=scheduled_time,
        )
        session.add(scheduled_post)
        session.flush()

        assert scheduled_post.id is not None
        assert scheduled_post.status == ScheduleStatus.PENDING
        assert scheduled_post.retry_count == 0

    def test_can_retry_when_failed(self, session, sample_account_data, sample_content_data):
        """Test can_retry is True when failed with retries remaining."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        content = Content(account_id=account.id, **sample_content_data)
        session.add(content)
        session.flush()

        scheduled_post = ScheduledPost(
            account_id=account.id,
            content_id=content.id,
            scheduled_time=datetime.now(timezone.utc),
            status=ScheduleStatus.FAILED,
            retry_count=1,
            max_retries=3,
        )
        session.add(scheduled_post)
        session.flush()

        assert scheduled_post.can_retry is True

    def test_cannot_retry_max_reached(self, session, sample_account_data, sample_content_data):
        """Test can_retry is False when max retries reached."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        content = Content(account_id=account.id, **sample_content_data)
        session.add(content)
        session.flush()

        scheduled_post = ScheduledPost(
            account_id=account.id,
            content_id=content.id,
            scheduled_time=datetime.now(timezone.utc),
            status=ScheduleStatus.FAILED,
            retry_count=3,
            max_retries=3,
        )
        session.add(scheduled_post)
        session.flush()

        assert scheduled_post.can_retry is False


class TestEngagementMetric:
    """Tests for EngagementMetric model."""

    def test_create_metric(self, session, sample_account_data):
        """Test creating an engagement metric."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        metric = EngagementMetric(
            account_id=account.id,
            instagram_media_id="media_123",
            recorded_at=datetime.now(timezone.utc),
            impressions=1000,
            reach=800,
            likes=100,
            comments=20,
            shares=10,
            saves=15,
        )
        session.add(metric)
        session.flush()

        assert metric.id is not None

    def test_engagement_rate(self, session, sample_account_data):
        """Test engagement rate calculation."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        metric = EngagementMetric(
            account_id=account.id,
            instagram_media_id="media_123",
            recorded_at=datetime.now(timezone.utc),
            reach=1000,
            likes=100,
            comments=20,
            shares=10,
        )
        session.add(metric)
        session.flush()

        # (100 + 20 + 10) / 1000 * 100 = 13%
        assert metric.engagement_rate == 13.0

    def test_engagement_rate_no_reach(self, session, sample_account_data):
        """Test engagement rate with no reach returns None."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        metric = EngagementMetric(
            account_id=account.id,
            instagram_media_id="media_123",
            recorded_at=datetime.now(timezone.utc),
            likes=100,
        )
        session.add(metric)
        session.flush()

        assert metric.engagement_rate is None

    def test_total_interactions(self, session, sample_account_data):
        """Test total interactions calculation."""
        account = InstagramAccount(**sample_account_data)
        session.add(account)
        session.flush()

        metric = EngagementMetric(
            account_id=account.id,
            instagram_media_id="media_123",
            recorded_at=datetime.now(timezone.utc),
            likes=100,
            comments=20,
            shares=10,
            saves=15,
        )
        session.add(metric)
        session.flush()

        assert metric.total_interactions == 145
