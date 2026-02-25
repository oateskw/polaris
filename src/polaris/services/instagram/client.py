"""Instagram Graph API client with rate limiting."""

from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential

from polaris.config import Settings, get_settings


class InstagramClientError(Exception):
    """Base exception for Instagram client errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class RateLimitError(InstagramClientError):
    """Rate limit exceeded error."""

    pass


class AuthenticationError(InstagramClientError):
    """Authentication error."""

    pass


class InstagramClient:
    """Client for Instagram Graph API with rate limiting."""

    BASE_URL = "https://graph.instagram.com"
    GRAPH_URL = "https://graph.facebook.com/v18.0"

    # Rate limits: 200 calls per hour per user
    CALLS_PER_HOUR = 200
    PERIOD = 3600  # 1 hour in seconds

    def __init__(
        self,
        access_token: str,
        instagram_user_id: str,
        settings: Optional[Settings] = None,
    ):
        self.access_token = access_token
        self.instagram_user_id = instagram_user_id
        self.settings = settings or get_settings()
        self._client = httpx.Client(timeout=30.0)

    def __enter__(self) -> "InstagramClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    @sleep_and_retry
    @limits(calls=CALLS_PER_HOUR, period=PERIOD)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def _make_request(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Make a rate-limited API request."""
        params = params or {}
        params["access_token"] = self.access_token

        response = self._client.request(method, url, params=params, json=json)

        if response.status_code == 429:
            raise RateLimitError(
                "Rate limit exceeded",
                status_code=response.status_code,
                response=response.json() if response.content else None,
            )

        if response.status_code == 401:
            raise AuthenticationError(
                "Invalid or expired access token",
                status_code=response.status_code,
                response=response.json() if response.content else None,
            )

        if response.status_code >= 400:
            error_data = response.json() if response.content else {}
            error_message = error_data.get("error", {}).get("message", "Unknown error")
            raise InstagramClientError(
                f"API error: {error_message}",
                status_code=response.status_code,
                response=error_data,
            )

        return response.json()

    def get_account_info(self) -> dict[str, Any]:
        """Get Instagram account information."""
        url = f"{self.BASE_URL}/{self.instagram_user_id}"
        params = {
            "fields": "id,username,name,profile_picture_url,followers_count,follows_count,media_count"
        }
        return self._make_request("GET", url, params=params)

    def get_media(self, limit: int = 25) -> list[dict[str, Any]]:
        """Get recent media from the account."""
        url = f"{self.BASE_URL}/{self.instagram_user_id}/media"
        params = {
            "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,like_count,comments_count",
            "limit": limit,
        }
        response = self._make_request("GET", url, params=params)
        return response.get("data", [])

    def get_media_insights(self, media_id: str) -> dict[str, Any]:
        """Get insights for a specific media post."""
        url = f"{self.BASE_URL}/{media_id}/insights"
        params = {
            "metric": "impressions,reach,saved,shares"
        }
        return self._make_request("GET", url, params=params)

    def get_account_insights(
        self,
        metric: str = "impressions,reach,follower_count",
        period: str = "day",
    ) -> dict[str, Any]:
        """Get account-level insights."""
        url = f"{self.BASE_URL}/{self.instagram_user_id}/insights"
        params = {
            "metric": metric,
            "period": period,
        }
        return self._make_request("GET", url, params=params)

    def create_carousel_item_container(self, image_url: str) -> str:
        """Create a media container for a single carousel item."""
        url = f"{self.GRAPH_URL}/{self.instagram_user_id}/media"
        params = {
            "image_url": image_url,
            "is_carousel_item": "true",
        }
        response = self._make_request("POST", url, params=params)
        return response["id"]

    def create_carousel_container(self, children: list[str], caption: str) -> str:
        """Create a carousel container from item container IDs."""
        url = f"{self.GRAPH_URL}/{self.instagram_user_id}/media"
        params = {
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption,
        }
        response = self._make_request("POST", url, params=params)
        return response["id"]

    def create_media_container(
        self,
        image_url: str,
        caption: str,
        is_carousel_item: bool = False,
    ) -> str:
        """Create a media container for publishing."""
        url = f"{self.GRAPH_URL}/{self.instagram_user_id}/media"
        params = {
            "image_url": image_url,
            "caption": caption,
        }
        if is_carousel_item:
            params["is_carousel_item"] = "true"

        response = self._make_request("POST", url, params=params)
        return response["id"]

    def create_video_container(
        self,
        video_url: str,
        caption: str,
        media_type: str = "REELS",
    ) -> str:
        """Create a video container for publishing."""
        url = f"{self.GRAPH_URL}/{self.instagram_user_id}/media"
        params = {
            "video_url": video_url,
            "caption": caption,
            "media_type": media_type,
        }
        response = self._make_request("POST", url, params=params)
        return response["id"]

    def create_story_container(self, image_url: str) -> str:
        """Create a media container for an Instagram Story image.

        Args:
            image_url: Publicly accessible HTTPS URL of the image (9:16 recommended)

        Returns:
            Container ID ready for publishing
        """
        url = f"{self.GRAPH_URL}/{self.instagram_user_id}/media"
        params = {
            "image_url": image_url,
            "media_type": "STORIES",
        }
        response = self._make_request("POST", url, params=params)
        return response["id"]

    def create_story_video_container(self, video_url: str) -> str:
        """Create a media container for an Instagram Story video.

        Args:
            video_url: Publicly accessible HTTPS URL of the video (9:16 recommended)

        Returns:
            Container ID ready for publishing
        """
        url = f"{self.GRAPH_URL}/{self.instagram_user_id}/media"
        params = {
            "video_url": video_url,
            "media_type": "STORIES",
        }
        response = self._make_request("POST", url, params=params)
        return response["id"]

    def check_container_status(self, container_id: str) -> dict[str, Any]:
        """Check the status of a media container."""
        url = f"{self.GRAPH_URL}/{container_id}"
        params = {"fields": "status_code,status"}
        return self._make_request("GET", url, params=params)

    def publish_media(self, container_id: str) -> str:
        """Publish a media container."""
        url = f"{self.GRAPH_URL}/{self.instagram_user_id}/media_publish"
        params = {"creation_id": container_id}
        response = self._make_request("POST", url, params=params)
        return response["id"]

    def get_hashtag_id(self, hashtag: str) -> str:
        """Get the ID for a hashtag."""
        url = f"{self.GRAPH_URL}/ig_hashtag_search"
        params = {
            "user_id": self.instagram_user_id,
            "q": hashtag.lstrip("#"),
        }
        response = self._make_request("GET", url, params=params)
        data = response.get("data", [])
        if not data:
            raise InstagramClientError(f"Hashtag '{hashtag}' not found")
        return data[0]["id"]

    def get_hashtag_recent_media(self, hashtag_id: str, limit: int = 25) -> list[dict[str, Any]]:
        """Get recent media for a hashtag."""
        url = f"{self.GRAPH_URL}/{hashtag_id}/recent_media"
        params = {
            "user_id": self.instagram_user_id,
            "fields": "id,caption,media_type,like_count,comments_count",
            "limit": limit,
        }
        response = self._make_request("GET", url, params=params)
        return response.get("data", [])
