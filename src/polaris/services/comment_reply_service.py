"""Auto-reply to public comments on recent Instagram posts using Claude."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from polaris.models.account import InstagramAccount
from polaris.models.comment_reply import CommentReply
from polaris.services.ai.claude_client import ClaudeClient
from polaris.services.instagram.client import InstagramClient
from polaris.services.instagram.messenger import InstagramMessenger
from polaris.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

_REPLY_PROMPT = """You are the social media voice for Polaris Innovations — an AI automation company for small businesses.

Someone commented on one of our Instagram posts. Write a short, warm, public reply.

Post topic: {topic}
Commenter: @{username}
Their comment: "{comment}"

Rules:
- 1-2 sentences max
- Sound human and genuine — not corporate or robotic
- If they asked a question, give a brief helpful answer
- If it's positive/supportive, thank them and add one line of value
- If it's skeptical, acknowledge it briefly and stay confident
- Never use hashtags
- Never use emojis unless they used them first
- Never mention "AI wrote this" or break the fourth wall
- End with something that invites further conversation naturally

Reply only — no labels, no quotes around the reply."""


class CommentReplyService:
    """Polls recent posts for new comments and replies to each one publicly."""

    # How many recent posts to monitor
    POSTS_TO_MONITOR = 10

    def __init__(self, session: Session, account: InstagramAccount):
        self.session = session
        self.account = account
        self.client = InstagramClient(
            access_token=account.access_token,
            instagram_user_id=account.instagram_user_id,
        )
        self.messenger = InstagramMessenger(self.client)
        self.claude = ClaudeClient()
        self.notifier = NotificationService()

    def run(self) -> int:
        """Poll recent posts and reply to any new comments.

        Returns the number of replies posted.
        """
        media_ids = self.client.get_recent_media_ids(limit=self.POSTS_TO_MONITOR)
        total_replied = 0

        for media_id in media_ids:
            try:
                total_replied += self._process_post(media_id)
            except Exception as e:
                logger.error(f"Error processing post {media_id}: {e}")

        return total_replied

    def _process_post(self, media_id: str) -> int:
        """Fetch comments on a post and reply to any we haven't replied to yet."""
        comments = self.messenger.get_post_comments(media_id)
        replied = 0

        for comment in comments:
            comment_id = comment.get("id", "")
            username = comment.get("username", "")
            text = comment.get("text", "")

            if not comment_id or not text:
                continue

            # Skip our own comments
            if username == self.account.username:
                continue

            # Skip if already replied
            if self._already_replied(comment_id):
                continue

            # Generate and post the reply
            try:
                reply = self._generate_reply(username, text, media_id)
                self.messenger.reply_to_comment(comment_id, reply)
                self._record_reply(media_id, comment_id, username, text, reply)
                self.session.commit()
                replied += 1
                logger.info(f"Replied to @{username} on post {media_id}")
            except Exception as e:
                logger.error(f"Failed to reply to comment {comment_id} (@{username}): {e}")

        return replied

    def _already_replied(self, comment_id: str) -> bool:
        """Check if we've already replied to this comment."""
        existing = self.session.query(CommentReply).filter_by(
            comment_id=comment_id
        ).first()
        return existing is not None

    def _generate_reply(self, username: str, comment: str, media_id: str) -> str:
        """Use Claude to generate a contextual public reply."""
        # Try to get the post topic from our content records
        topic = self._get_post_topic(media_id)

        prompt = _REPLY_PROMPT.format(
            topic=topic,
            username=username,
            comment=comment,
        )
        reply = self.claude.generate(prompt=prompt, temperature=0.8, max_tokens=120)
        return reply.strip()

    def _get_post_topic(self, media_id: str) -> str:
        """Look up the post topic from our content records if available."""
        from polaris.models.content import Content
        content = self.session.query(Content).filter_by(
            instagram_media_id=media_id
        ).first()
        if content and content.topic:
            return content.topic
        return "AI automation for small businesses"

    def _record_reply(
        self,
        media_id: str,
        comment_id: str,
        username: str,
        comment_text: str,
        reply_text: str,
    ) -> None:
        """Save a record of the reply for deduplication."""
        record = CommentReply(
            account_id=self.account.id,
            post_media_id=media_id,
            comment_id=comment_id,
            commenter_username=username,
            comment_text=comment_text[:500],
            reply_text=reply_text[:500],
            replied_at=datetime.now(timezone.utc),
        )
        self.session.add(record)
