"""Tests for service classes."""

from unittest.mock import MagicMock, patch

import pytest

from polaris.services.ai.content_generator import ContentGenerator, ContentIdea, GeneratedCaption
from polaris.services.ai.prompts import BRAND_CONTEXT


class TestContentGenerator:
    """Tests for ContentGenerator service."""

    def test_generate_caption(self):
        """Test caption generation."""
        mock_client = MagicMock()
        mock_client.generate.side_effect = [
            "This is a test caption about AI innovations in tech.",
            "#tech #ai #innovation #polaris #software",
        ]
        mock_client.DEFAULT_MODEL = "claude-sonnet-4-20250514"

        generator = ContentGenerator(client=mock_client)
        result = generator.generate_caption("AI innovations", context="product launch")

        assert isinstance(result, GeneratedCaption)
        assert "test caption" in result.caption
        assert "#tech" in result.hashtags
        assert result.topic == "AI innovations"
        assert mock_client.generate.call_count == 2

    def test_generate_hashtags(self):
        """Test hashtag generation."""
        mock_client = MagicMock()
        mock_client.generate.return_value = "#tech #ai #innovation"

        generator = ContentGenerator(client=mock_client)
        result = generator.generate_hashtags("AI innovations")

        assert "#tech" in result
        assert "#ai" in result

    def test_generate_hashtags_formatting(self):
        """Test hashtag formatting without # prefix."""
        mock_client = MagicMock()
        mock_client.generate.return_value = "tech ai innovation"  # No # prefix

        generator = ContentGenerator(client=mock_client)
        result = generator.generate_hashtags("AI innovations")

        assert "#tech" in result
        assert "#ai" in result
        assert "#innovation" in result

    def test_generate_content_ideas(self):
        """Test content ideas generation."""
        mock_client = MagicMock()
        mock_client.generate.return_value = """
---
Title: AI in Software Development
Description: Explore how AI is transforming the way we write code.
Media Type: carousel
Key Message: AI tools are becoming essential for developers.
---
Title: Cloud Computing Trends
Description: The latest trends in cloud infrastructure.
Media Type: image
Key Message: Cloud-native is the future.
---
"""

        generator = ContentGenerator(client=mock_client)
        ideas = generator.generate_content_ideas(count=2)

        assert len(ideas) == 2
        assert isinstance(ideas[0], ContentIdea)
        assert "AI" in ideas[0].title
        assert ideas[0].media_type == "carousel"
        assert ideas[1].media_type == "image"

    def test_improve_caption(self):
        """Test caption improvement."""
        mock_client = MagicMock()
        mock_client.generate.return_value = "Improved caption with better engagement."

        generator = ContentGenerator(client=mock_client)
        result = generator.improve_caption(
            "Original caption",
            improvement_focus="engagement",
        )

        assert "Improved" in result
        mock_client.generate.assert_called_once()


class TestInstagramClientMocked:
    """Tests for InstagramClient with mocked HTTP."""

    def test_get_account_info(self):
        """Test getting account info."""
        from polaris.services.instagram.client import InstagramClient

        with patch("httpx.Client") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "123456",
                "username": "testuser",
                "followers_count": 1000,
            }
            mock_httpx.return_value.__enter__.return_value.request.return_value = mock_response

            client = InstagramClient(
                access_token="test_token",
                instagram_user_id="123456",
            )
            # Mock the internal client
            client._client = MagicMock()
            client._client.request.return_value = mock_response

            info = client.get_account_info()

            assert info["username"] == "testuser"
            assert info["followers_count"] == 1000

    def test_rate_limit_error(self):
        """Test rate limit error handling."""
        from polaris.services.instagram.client import InstagramClient, RateLimitError

        with patch("httpx.Client") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.content = b'{"error": "rate limited"}'
            mock_response.json.return_value = {"error": "rate limited"}

            client = InstagramClient(
                access_token="test_token",
                instagram_user_id="123456",
            )
            client._client = MagicMock()
            client._client.request.return_value = mock_response

            with pytest.raises(RateLimitError):
                client.get_account_info()


class TestInstagramPublisherMocked:
    """Tests for InstagramPublisher with mocked client."""

    def test_publish_image(self):
        """Test publishing an image."""
        from polaris.services.instagram.client import InstagramClient
        from polaris.services.instagram.publisher import InstagramPublisher

        mock_client = MagicMock(spec=InstagramClient)
        mock_client.create_media_container.return_value = "container_123"
        mock_client.check_container_status.return_value = {"status_code": "FINISHED"}
        mock_client.publish_media.return_value = "media_456"

        publisher = InstagramPublisher(mock_client)
        media_id = publisher.publish_image(
            image_url="https://example.com/image.jpg",
            caption="Test caption",
        )

        assert media_id == "media_456"
        mock_client.create_media_container.assert_called_once()
        mock_client.publish_media.assert_called_once_with("container_123")

    def test_publish_content_image(self):
        """Test publishing content object."""
        from polaris.models.content import Content, ContentType
        from polaris.services.instagram.client import InstagramClient
        from polaris.services.instagram.publisher import InstagramPublisher

        mock_client = MagicMock(spec=InstagramClient)
        mock_client.create_media_container.return_value = "container_123"
        mock_client.check_container_status.return_value = {"status_code": "FINISHED"}
        mock_client.publish_media.return_value = "media_456"

        # Create a mock content object
        content = MagicMock(spec=Content)
        content.media_url = "https://example.com/image.jpg"
        content.media_type = ContentType.IMAGE
        content.full_caption = "Test caption #hashtags"

        publisher = InstagramPublisher(mock_client)
        media_id = publisher.publish_content(content)

        assert media_id == "media_456"

    def test_publish_content_no_media_url(self):
        """Test publishing content without media URL raises error."""
        from polaris.models.content import Content
        from polaris.services.instagram.client import InstagramClient
        from polaris.services.instagram.publisher import InstagramPublisher, PublishError

        mock_client = MagicMock(spec=InstagramClient)

        content = MagicMock(spec=Content)
        content.media_url = None

        publisher = InstagramPublisher(mock_client)

        with pytest.raises(PublishError, match="must have a media URL"):
            publisher.publish_content(content)
