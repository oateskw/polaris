"""Email notification service for lead alerts."""

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from polaris.config import Settings, get_settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Sends email notifications when leads come in."""

    def __init__(self, settings: Settings = None):
        self.settings = settings or get_settings()

    def notify_new_lead(self, lead: Any, trigger: Any) -> bool:
        """Send an email notification for a new lead.

        Args:
            lead: Lead model instance
            trigger: CommentTrigger model instance

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.settings.is_email_configured:
            return False

        try:
            subject = f"New lead from @{lead.commenter_username} — Polaris"
            body = self._build_lead_email(lead, trigger)
            self._send(subject, body)
            logger.info(f"Lead notification sent for lead #{lead.id} (@{lead.commenter_username})")
            return True
        except Exception as e:
            logger.error(f"Failed to send lead notification: {e}")
            return False

    def notify_lead_replied(self, lead: Any, message: str) -> bool:
        """Send an email notification when a lead replies to the DM.

        Args:
            lead: Lead model instance
            message: The reply message from the lead

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.settings.is_email_configured:
            return False

        try:
            subject = f"@{lead.commenter_username} replied to your DM — Polaris"
            body = self._build_reply_email(lead, message)
            self._send(subject, body)
            logger.info(f"Reply notification sent for lead #{lead.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send reply notification: {e}")
            return False

    def _build_lead_email(self, lead: Any, trigger: Any) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"""New lead captured by Polaris!

Instagram User:  @{lead.commenter_username}
Comment:         "{lead.comment_text}"
Keyword:         {trigger.keyword}
Post ID:         {lead.post_instagram_media_id}
Time:            {now}

Initial DM sent:
"{trigger.initial_message}"

---
View full conversation:
  python -m polaris leads show {lead.id}

View all leads:
  python -m polaris leads list
"""

    def _build_reply_email(self, lead: Any, message: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        history = lead.conversation_history or []
        turns = len([h for h in history if h.get("role") == "user"])
        return f"""@{lead.commenter_username} replied to your DM!

Message:    "{message}"
Time:       {now}
Lead ID:    #{lead.id}
Replies so far: {turns}

---
View full conversation:
  python -m polaris leads show {lead.id}
"""

    def _send(self, subject: str, body: str) -> None:
        recipients = self.settings.notification_emails
        if not recipients:
            return

        msg = MIMEMultipart()
        msg["From"] = self.settings.smtp_username
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as server:
            server.starttls()
            server.login(self.settings.smtp_username, self.settings.smtp_password)
            server.sendmail(self.settings.smtp_username, recipients, msg.as_string())
