"""Lead service — orchestrates comment polling, DM sending, and AI follow-up."""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from polaris.models.account import InstagramAccount
from polaris.models.lead import LeadStatus
from polaris.repositories.lead_repository import (
    CommentTriggerRepository,
    LeadRepository,
)
from polaris.services.ai.lead_responder import LeadResponder
from polaris.services.instagram.client import InstagramClient
from polaris.services.instagram.messenger import InstagramMessenger
from polaris.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class LeadService:
    """Orchestrates the full comment-to-DM lead automation pipeline."""

    def __init__(self, session: Session, account: InstagramAccount):
        self.session = session
        self.account = account

        client = InstagramClient(
            access_token=account.access_token,
            instagram_user_id=account.instagram_user_id,
        )
        self.messenger = InstagramMessenger(client)
        self.trigger_repo = CommentTriggerRepository(session)
        self.lead_repo = LeadRepository(session)
        self.lead_responder = LeadResponder()
        self.notifier = NotificationService()

    # ------------------------------------------------------------------
    # Comment trigger polling
    # ------------------------------------------------------------------

    def poll_triggers(self) -> int:
        """Check all active triggers for new keyword-matching comments.

        Returns number of new leads created.
        """
        triggers = self.trigger_repo.get_active_for_account(self.account.id)
        new_leads = 0

        for trigger in triggers:
            try:
                new_leads += self._process_trigger(trigger)
            except Exception as e:
                logger.error(f"Error processing trigger {trigger.id}: {e}")

        return new_leads

    def _process_trigger(self, trigger: Any) -> int:
        """Fetch new comments on a post, match keyword, send DMs, create leads."""
        since = trigger.last_polled_at
        comments = self.messenger.get_post_comments(
            media_id=trigger.post_instagram_media_id,
            since=since,
        )

        new_leads = 0
        had_delivery_failures = False
        keyword = trigger.keyword.lower()

        for comment in comments:
            comment_text = comment.get("text", "")
            if keyword not in comment_text.lower():
                continue

            comment_id = comment.get("id", "")
            if not comment_id:
                continue

            # Deduplication: skip if we already have a lead for this comment
            existing = self.lead_repo.get_by_comment_id(comment_id)
            if existing:
                continue

            ig_user_id = comment.get("ig_user_id", "")
            username = comment.get("username", "unknown")

            # Send a true DM first; fallback to private-reply if direct DM is blocked.
            delivered = False
            if ig_user_id:
                try:
                    self.messenger.send_message(ig_user_id, trigger.initial_message)
                    delivered = True
                    logger.info(
                        f"Sent initial DM to @{username} (ig_user_id={ig_user_id}) "
                        f"for comment {comment_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Direct DM failed for @{username} (ig_user_id={ig_user_id}) "
                        f"on comment {comment_id}: {e}. Trying private reply fallback."
                    )

            if not delivered:
                try:
                    self.messenger.send_private_reply(
                        comment_id, trigger.initial_message
                    )
                    delivered = True
                    logger.info(
                        f"Sent private-reply fallback to @{username} for comment {comment_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to deliver initial outreach for comment {comment_id} "
                        f"(user: {username}): {e}"
                    )
                    had_delivery_failures = True
                    continue

            # Create lead record
            lead = self.lead_repo.create_lead(
                account_id=self.account.id,
                trigger_id=trigger.id,
                commenter_ig_user_id=ig_user_id,
                commenter_username=username,
                post_instagram_media_id=trigger.post_instagram_media_id,
                comment_id=comment_id,
                comment_text=comment_text,
            )

            # Record initial DM in conversation history
            now = datetime.now(timezone.utc)
            history = [
                {
                    "role": "assistant",
                    "message": trigger.initial_message,
                    "timestamp": now.isoformat(),
                }
            ]
            self.lead_repo.update_conversation(lead.id, history)
            self.lead_repo.mark_dm_sent(lead.id, sent_at=now)

            self.session.commit()
            new_leads += 1
            logger.info(
                f"Created lead #{lead.id} for @{username} "
                f"(trigger {trigger.id}, comment {comment_id})"
            )
            self.notifier.notify_new_lead(lead, trigger)

        # Advance polling cursor only if all matched comments were deliverable.
        # If delivery failed for any match, keep cursor unchanged so it can retry.
        if had_delivery_failures:
            logger.warning(
                f"Keeping last_polled_at unchanged for trigger {trigger.id} "
                "because at least one initial outreach delivery failed"
            )
        else:
            self.trigger_repo.update_last_polled(trigger.id, datetime.now(timezone.utc))
        self.session.commit()

        return new_leads

    # ------------------------------------------------------------------
    # Inbound DM trigger polling (alternative to comment triggers)
    # ------------------------------------------------------------------

    def poll_inbound_dm_triggers(self) -> int:
        """Check for inbound DMs matching active trigger keywords.

        This bypasses the Instagram messaging window restriction because
        the user initiated the conversation. Returns number of new leads created.
        """
        triggers = self.trigger_repo.get_active_for_account(self.account.id)
        if not triggers:
            return 0

        # Fetch all recent inbound messages
        try:
            messages = self.messenger.get_recent_inbound_messages(
                since=None  # Fetch all for now; filtering by trigger.last_polled_at is optional
            )
        except Exception as e:
            logger.error(f"Failed to fetch inbound DM messages: {e}")
            return 0

        new_leads = 0
        keyword_to_trigger = {t.keyword.lower(): t for t in triggers}

        for msg in messages:
            msg_text_raw = msg.get("text", "")
            msg_text = msg_text_raw.lower()
            msg_text_normalized = msg_text.strip()
            from_user_id = msg.get("from_ig_user_id", "")
            from_username = msg.get("from_username", "unknown")
            message_id = msg.get("id", "")

            if not from_user_id or not message_id:
                continue

            # Check if this message matches any active trigger
            matched_trigger = None
            for keyword, trigger in keyword_to_trigger.items():
                if msg_text_normalized == keyword:
                    matched_trigger = trigger
                    break

            if not matched_trigger:
                continue

            # Deduplication: skip if we already have a lead for this message
            existing = self.lead_repo.get_by_inbound_message_id(message_id)
            if existing:
                logger.debug(f"Skipping duplicate inbound message {message_id}")
                continue

            # If this user already has an active lead for this trigger, do not
            # restart outreach; let poll_conversations handle ongoing replies.
            open_lead = self.lead_repo.get_open_by_user_and_trigger(
                account_id=self.account.id,
                trigger_id=matched_trigger.id,
                commenter_ig_user_id=from_user_id,
            )
            if open_lead:
                logger.debug(
                    f"Skipping new lead for @{from_username} on trigger {matched_trigger.id}; "
                    f"existing open lead #{open_lead.id}"
                )
                continue

            # Send initial response
            try:
                self.messenger.send_message(
                    from_user_id, matched_trigger.initial_message
                )
                logger.info(
                    f"Sent initial DM response to @{from_username} (ig_user_id={from_user_id}) "
                    f"for inbound message {message_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to send DM response to @{from_username} "
                    f"for inbound message {message_id}: {e}"
                )
                continue

            # Create lead record (use a placeholder post_media_id since there's no post)
            lead = self.lead_repo.create_lead(
                account_id=self.account.id,
                trigger_id=matched_trigger.id,
                commenter_ig_user_id=from_user_id,
                commenter_username=from_username,
                post_instagram_media_id="0",  # Placeholder; inbound DM doesn't have a post
                comment_id=None,
                comment_text=msg_text_raw,
                inbound_message_id=message_id,
            )

            # Record initial DM in conversation history
            now = datetime.now(timezone.utc)
            history = [
                {
                    "role": "user",
                    "message": msg_text_raw,
                    "timestamp": msg.get("created_time", now.isoformat()),
                },
                {
                    "role": "assistant",
                    "message": matched_trigger.initial_message,
                    "timestamp": now.isoformat(),
                },
            ]
            self.lead_repo.update_conversation(lead.id, history)
            self.lead_repo.mark_dm_sent(lead.id, sent_at=now)

            self.session.commit()
            new_leads += 1
            logger.info(
                f"Created lead #{lead.id} for @{from_username} "
                f"(trigger {matched_trigger.id}, inbound message {message_id})"
            )
            self.notifier.notify_new_lead(lead, matched_trigger)

        return new_leads

    # ------------------------------------------------------------------
    # Conversation polling (AI follow-up)
    # ------------------------------------------------------------------

    def poll_conversations(self) -> int:
        """Check DM threads for new replies from CONTACTED leads and respond with AI.

        Returns number of AI replies sent.
        """
        if not self._has_follow_up_enabled():
            return 0

        leads = self.lead_repo.get_open_for_follow_up(self.account.id)
        if not leads:
            return 0

        # Fetch all conversations once to avoid hammering the API
        try:
            conversations = self.messenger.get_conversations()
        except Exception as e:
            logger.error(f"Failed to fetch conversations: {e}")
            return 0

        replies_sent = 0

        for lead in leads:
            try:
                sent = self._process_lead_conversation(lead, conversations)
                if sent:
                    replies_sent += 1
            except Exception as e:
                logger.error(f"Error processing conversation for lead {lead.id}: {e}")

        return replies_sent

    def _has_follow_up_enabled(self) -> bool:
        """Return True if any active trigger has follow_up_enabled."""
        triggers = self.trigger_repo.get_active_for_account(self.account.id)
        return any(t.follow_up_enabled for t in triggers)

    def _process_lead_conversation(self, lead: Any, conversations: list) -> bool:
        """Check if a lead has replied and send an AI response if so."""
        ig_user_id = lead.commenter_ig_user_id
        history = lead.conversation_history or []

        # Find the conversation thread for this lead
        thread = self._find_thread(conversations, ig_user_id)
        if not thread:
            return False

        # Find messages newer than the last history entry
        last_timestamp = self._last_message_timestamp(history)
        new_user_messages = self._extract_new_user_messages(
            thread, ig_user_id, last_timestamp
        )

        if not new_user_messages:
            return False

        # Append new user messages to history
        for msg in new_user_messages:
            history.append(
                {
                    "role": "user",
                    "message": msg["text"],
                    "timestamp": msg["timestamp"],
                }
            )

        # Generate AI reply
        try:
            post_context = self._build_post_context(lead)
            reply_text = self.lead_responder.generate_reply(
                commenter_username=lead.commenter_username,
                conversation_history=history,
                post_topic=post_context,
            )
        except Exception as e:
            logger.error(f"AI reply generation failed for lead {lead.id}: {e}")
            return False

        # Send the reply
        try:
            self.messenger.send_message(ig_user_id, reply_text)
        except Exception as e:
            logger.error(f"Failed to send AI reply for lead {lead.id}: {e}")
            return False

        # Update history and status
        history.append(
            {
                "role": "assistant",
                "message": reply_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.lead_repo.update_conversation(lead.id, history)
        if self._has_qualification_intent(new_user_messages):
            self.lead_repo.update_status(lead.id, LeadStatus.QUALIFIED)
        elif lead.status != LeadStatus.QUALIFIED:
            self.lead_repo.update_status(lead.id, LeadStatus.REPLIED)
        self.session.commit()

        logger.info(f"Sent AI reply to lead #{lead.id} (@{lead.commenter_username})")

        # Notify owner that the lead replied
        latest_user_msg = new_user_messages[-1]["text"] if new_user_messages else ""
        self.notifier.notify_lead_replied(lead, latest_user_msg)

        return True

    def _find_thread(self, conversations: list, ig_user_id: str) -> dict | None:
        """Return the conversation thread that involves a given user ID."""
        for conv in conversations:
            messages_data = conv.get("messages", {}).get("data", [])
            for msg in messages_data:
                from_data = msg.get("from", {})
                if from_data.get("id") == ig_user_id:
                    return conv
        return None

    def _last_message_timestamp(self, history: list) -> str | None:
        """Return the ISO timestamp of the last message in history, or None."""
        if not history:
            return None
        return history[-1].get("timestamp")

    def _extract_new_user_messages(
        self,
        thread: dict,
        ig_user_id: str,
        since_timestamp: str | None,
    ) -> list[dict]:
        """Extract user messages from a thread that are newer than since_timestamp."""
        messages_data = thread.get("messages", {}).get("data", [])
        result = []

        for msg in messages_data:
            from_data = msg.get("from", {})
            # Only include messages FROM the lead (not from us)
            if from_data.get("id") != ig_user_id:
                continue

            msg_time = msg.get("created_time", "")

            if since_timestamp and msg_time <= since_timestamp:
                continue

            result.append(
                {
                    "text": msg.get("message", ""),
                    "timestamp": msg_time,
                }
            )

        # Return in chronological order
        return sorted(result, key=lambda m: m["timestamp"])

    def _build_post_context(self, lead: Any) -> str:
        """Build concise post/trigger context for AI concierge responses."""
        parts: list[str] = []
        if getattr(lead, "trigger", None):
            keyword = getattr(lead.trigger, "keyword", "")
            if keyword:
                parts.append(f"Trigger keyword: {keyword}")
        if lead.comment_text:
            parts.append(f"Original comment: {lead.comment_text}")
        if lead.post_instagram_media_id:
            parts.append(f"Post media ID: {lead.post_instagram_media_id}")
        return " | ".join(parts)

    def _has_qualification_intent(self, new_user_messages: list[dict]) -> bool:
        """Detect buyer intent from recent user messages (pricing/booking/tasting)."""
        if not new_user_messages:
            return False

        intent_patterns = [
            r"\bprice\b",
            r"\bpricing\b",
            r"\bcost\b",
            r"\bquote\b",
            r"\brate\b",
            r"\bbook\b",
            r"\bbooking\b",
            r"\bschedule\b",
            r"\bavailable\b",
            r"\btasting\b",
            r"\bconsult\b",
            r"\bconsultation\b",
            r"\bdate\b",
            r"\bwedding date\b",
            r"\bpackage\b",
        ]
        combined = " ".join((m.get("text") or "") for m in new_user_messages).lower()
        return any(re.search(pattern, combined) for pattern in intent_patterns)
