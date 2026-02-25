"""Instagram media publishing service."""

import time
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from polaris.models.content import Content, ContentStatus, ContentType
from polaris.services.instagram.client import InstagramClient, InstagramClientError


class PublishError(Exception):
    """Error during media publishing."""

    pass


class InstagramPublisher:
    """Service for publishing content to Instagram."""

    CONTAINER_CHECK_INTERVAL = 5  # seconds
    CONTAINER_MAX_WAIT = 300  # 5 minutes

    def __init__(self, client: InstagramClient):
        self.client = client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def publish_image(
        self,
        image_url: str,
        caption: str,
    ) -> str:
        """Publish a single image post.

        Args:
            image_url: URL of the image to publish (must be publicly accessible)
            caption: Caption for the post

        Returns:
            Instagram media ID of the published post
        """
        # Create media container
        container_id = self.client.create_media_container(
            image_url=image_url,
            caption=caption,
        )

        # Wait for container to be ready
        self._wait_for_container(container_id)

        # Publish the media
        media_id = self.client.publish_media(container_id)
        return media_id

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def publish_video(
        self,
        video_url: str,
        caption: str,
        media_type: str = "REELS",
    ) -> str:
        """Publish a video or reel.

        Args:
            video_url: URL of the video to publish (must be publicly accessible)
            caption: Caption for the post
            media_type: Type of video content (REELS or VIDEO)

        Returns:
            Instagram media ID of the published post
        """
        # Create video container
        container_id = self.client.create_video_container(
            video_url=video_url,
            caption=caption,
            media_type=media_type,
        )

        # Wait for container to be ready (videos take longer)
        self._wait_for_container(container_id, max_wait=600)

        # Publish the media
        media_id = self.client.publish_media(container_id)
        return media_id

    def publish_carousel(self, image_urls: list[str], caption: str) -> str:
        """Publish a carousel (multi-image) post.

        Args:
            image_urls: List of publicly accessible image URLs (2-10 images)
            caption: Caption for the carousel post

        Returns:
            Instagram media ID of the published post
        """
        # Create item containers for each image
        item_ids = [self.client.create_carousel_item_container(url) for url in image_urls]

        # Wait for each item to be ready
        for item_id in item_ids:
            self._wait_for_container(item_id)

        # Create the carousel container
        container_id = self.client.create_carousel_container(item_ids, caption)
        self._wait_for_container(container_id)

        return self.client.publish_media(container_id)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def publish_story(self, image_url: str) -> str:
        """Publish an image as an Instagram Story.

        Args:
            image_url: Publicly accessible HTTPS URL of the image.
                       9:16 aspect ratio (1080x1920) is strongly recommended.

        Returns:
            Instagram media ID of the published story
        """
        container_id = self.client.create_story_container(image_url)
        self._wait_for_container(container_id)
        return self.client.publish_media(container_id)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def publish_story_video(self, video_url: str) -> str:
        """Publish a video as an Instagram Story.

        Args:
            video_url: Publicly accessible HTTPS URL of the video.
                       9:16 aspect ratio is strongly recommended.

        Returns:
            Instagram media ID of the published story
        """
        container_id = self.client.create_story_video_container(video_url)
        self._wait_for_container(container_id, max_wait=600)
        return self.client.publish_media(container_id)

    def publish_content(self, content: Content) -> str:
        """Publish a Content object to Instagram.

        Args:
            content: Content model instance to publish

        Returns:
            Instagram media ID of the published post
        """
        if not content.media_url:
            raise PublishError("Content must have a media URL")

        caption = content.full_caption

        if content.media_type == ContentType.IMAGE:
            return self.publish_image(content.media_url, caption)
        elif content.media_type in (ContentType.VIDEO, ContentType.REEL):
            return self.publish_video(content.media_url, caption, media_type="REELS")
        elif content.media_type == ContentType.CAROUSEL:
            image_urls = [u.strip() for u in content.media_url.split("|") if u.strip()]
            if not image_urls:
                raise PublishError("Carousel content has no image URLs in media_url")
            return self.publish_carousel(image_urls, caption)
        else:
            raise PublishError(f"Unsupported media type: {content.media_type}")

    def _wait_for_container(
        self,
        container_id: str,
        max_wait: int = CONTAINER_MAX_WAIT,
    ) -> None:
        """Wait for a media container to be ready for publishing.

        Args:
            container_id: ID of the container to check
            max_wait: Maximum time to wait in seconds

        Raises:
            PublishError: If container fails or times out
        """
        elapsed = 0
        while elapsed < max_wait:
            status = self.client.check_container_status(container_id)
            status_code = status.get("status_code")

            if status_code == "FINISHED":
                return
            elif status_code == "ERROR":
                error_message = status.get("status", "Unknown error")
                raise PublishError(f"Container failed: {error_message}")
            elif status_code in ("EXPIRED", "IN_PROGRESS"):
                time.sleep(self.CONTAINER_CHECK_INTERVAL)
                elapsed += self.CONTAINER_CHECK_INTERVAL
            else:
                # Unknown status, wait and retry
                time.sleep(self.CONTAINER_CHECK_INTERVAL)
                elapsed += self.CONTAINER_CHECK_INTERVAL

        raise PublishError(f"Container timed out after {max_wait} seconds")

    def validate_image_url(self, url: str) -> bool:
        """Validate that an image URL is accessible.

        Note: Instagram requires images to be publicly accessible HTTPS URLs.
        """
        import httpx

        try:
            response = httpx.head(url, follow_redirects=True, timeout=10)
            if response.status_code != 200:
                return False
            content_type = response.headers.get("content-type", "")
            return content_type.startswith("image/")
        except Exception:
            return False

    def validate_video_url(self, url: str) -> bool:
        """Validate that a video URL is accessible.

        Note: Instagram requires videos to be publicly accessible HTTPS URLs.
        """
        import httpx

        try:
            response = httpx.head(url, follow_redirects=True, timeout=10)
            if response.status_code != 200:
                return False
            content_type = response.headers.get("content-type", "")
            return content_type.startswith("video/")
        except Exception:
            return False
