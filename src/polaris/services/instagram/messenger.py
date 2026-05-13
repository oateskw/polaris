"""Instagram messaging service for comment-to-DM automation."""

import logging
from datetime import datetime
from typing import Any, Optional

from polaris.services.instagram.client import InstagramClient

logger = logging.getLogger(__name__)


class InstagramMessenger:
    """Wraps Instagram Graph API messaging and comment endpoints."""

    def __init__(self, client: InstagramClient):
        self.client = client

    def get_post_comments(
        self,
        media_id: str,
        since: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Fetch comments on a post, optionally filtered by time.

        Returns list of dicts with keys: id, text, username, ig_user_id, timestamp
        """
        url = f"{self.client.GRAPH_URL}/{media_id}/comments"
        params = {
            "fields": "id,text,username,from,timestamp",
            "limit": 100,
        }
        if since is not None:
            # Instagram API accepts Unix timestamp for since parameter
            params["since"] = int(since.timestamp())

        try:
            response = self.client._make_request("GET", url, params=params)
            raw_comments = response.get("data", [])
        except Exception as e:
            logger.error(f"Failed to fetch comments for media {media_id}: {e}")
            return []

        comments = []
        for c in raw_comments:
            from_data = c.get("from", {})
            comments.append({
                "id": c.get("id", ""),
                "text": c.get("text", ""),
                "username": c.get("username", "") or from_data.get("username", ""),
                "ig_user_id": from_data.get("id", ""),
                "timestamp": c.get("timestamp", ""),
            })
        return comments

    def send_private_reply(self, comment_id: str, message: str) -> dict[str, Any]:
        """Send a private reply (DM) to a comment via the private_replies endpoint.

        This bypasses the 24-hour messaging window.
        Requires: instagram_manage_messages permission.
        """
        url = f"{self.client.GRAPH_URL}/{comment_id}/private_replies"
        params = {"message": message}
        try:
            response = self.client._make_request("POST", url, params=params)
            logger.info(f"Sent private reply to comment {comment_id}")
            return response
        except Exception as e:
            logger.error(f"Failed to send private reply to comment {comment_id}: {e}")
            raise

    def get_conversations(self) -> list[dict[str, Any]]:
        """Fetch all DM conversations for the account.

        Returns list of conversation dicts, each containing messages.
        Requires: instagram_manage_messages permission.
        """
        url = f"{self.client.GRAPH_URL}/me/conversations"
        params = {
            "platform": "instagram",
            "fields": "messages{id,message,from,created_time}",
        }
        try:
            response = self.client._make_request("GET", url, params=params)
            return response.get("data", [])
        except Exception as e:
            logger.error(f"Failed to fetch conversations: {e}")
            return []

    def get_recent_inbound_messages(self, since: Optional[datetime] = None) -> list[dict[str, Any]]:
        """Fetch recent inbound messages from all conversations.

        Returns list of message dicts with keys: id, text, from_ig_user_id, from_username, created_time
        """
        conversations = self.get_conversations()
        messages = []

        for conv in conversations:
            messages_data = conv.get("messages", {}).get("data", [])
            for msg in messages_data:
                from_data = msg.get("from", {})
                from_id = from_data.get("id", "")

                # Skip messages we sent (from us)
                if from_id == self.client.instagram_user_id:
                    continue

                msg_timestamp_str = msg.get("created_time", "")
                if msg_timestamp_str and since:
                    try:
                        msg_dt = datetime.fromisoformat(msg_timestamp_str.replace("Z", "+00:00"))
                        if msg_dt < since:
                            continue
                    except (ValueError, TypeError):
                        pass

                messages.append({
                    "id": msg.get("id", ""),
                    "text": msg.get("message", ""),
                    "from_ig_user_id": from_id,
                    "from_username": from_data.get("username", ""),
                    "created_time": msg_timestamp_str,
                })

        return messages

    def reply_to_comment(self, comment_id: str, message: str) -> dict[str, Any]:
        """Post a public reply to a comment."""
        try:
            response = self.client.reply_to_comment(comment_id, message)
            logger.info(f"Posted public reply to comment {comment_id}")
            return response
        except Exception as e:
            logger.error(f"Failed to reply to comment {comment_id}: {e}")
            raise

    def send_message(self, recipient_ig_user_id: str, message: str) -> dict[str, Any]:
        """Send a DM to an Instagram user.

        Args:
            recipient_ig_user_id: The Instagram-scoped user ID of the recipient
            message: Text to send

        Returns:
            API response dict
        """
        url = f"{self.client.GRAPH_URL}/me/messages"
        json_body = {
            "recipient": {"id": recipient_ig_user_id},
            "message": {"text": message},
        }
        try:
            response = self.client._make_request("POST", url, json=json_body)
            logger.info(f"Sent DM to user {recipient_ig_user_id}")
            return response
        except Exception as e:
            logger.error(f"Failed to send DM to {recipient_ig_user_id}: {e}")
            raise
