"""Repositories for lead management models."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from polaris.models.lead import CommentTrigger, Lead, LeadStatus
from polaris.repositories.base_repository import BaseRepository


class CommentTriggerRepository(BaseRepository[CommentTrigger]):
    """Repository for CommentTrigger CRUD operations."""

    def __init__(self, session):
        super().__init__(session, CommentTrigger)

    def get_active(self) -> list[CommentTrigger]:
        """Return all triggers with is_active=True."""
        stmt = select(CommentTrigger).where(CommentTrigger.is_active == True)
        return list(self.session.execute(stmt).scalars().all())

    def get_active_for_account(self, account_id: int) -> list[CommentTrigger]:
        """Return active triggers for a specific account."""
        stmt = select(CommentTrigger).where(
            CommentTrigger.is_active == True,
            CommentTrigger.account_id == account_id,
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_by_post(self, post_instagram_media_id: str) -> list[CommentTrigger]:
        """Return all triggers watching a given post."""
        stmt = select(CommentTrigger).where(
            CommentTrigger.post_instagram_media_id == post_instagram_media_id
        )
        return list(self.session.execute(stmt).scalars().all())

    def create_trigger(
        self,
        account_id: int,
        post_instagram_media_id: str,
        keyword: str,
        initial_message: str,
        follow_up_enabled: bool = True,
    ) -> CommentTrigger:
        """Create a new CommentTrigger."""
        return self.create(
            account_id=account_id,
            post_instagram_media_id=post_instagram_media_id,
            keyword=keyword,
            initial_message=initial_message,
            follow_up_enabled=follow_up_enabled,
        )

    def deactivate(self, trigger_id: int) -> Optional[CommentTrigger]:
        """Set is_active=False on a trigger."""
        return self.update(trigger_id, is_active=False)

    def activate(self, trigger_id: int) -> Optional[CommentTrigger]:
        """Set is_active=True on a trigger."""
        return self.update(trigger_id, is_active=True)

    def update_last_polled(self, trigger_id: int, timestamp: datetime) -> Optional[CommentTrigger]:
        """Update last_polled_at cursor."""
        return self.update(trigger_id, last_polled_at=timestamp)


class LeadRepository(BaseRepository[Lead]):
    """Repository for Lead CRUD operations."""

    def __init__(self, session):
        super().__init__(session, Lead)

    def get_by_account(
        self,
        account_id: int,
        status: Optional[LeadStatus] = None,
        limit: int = 100,
    ) -> list[Lead]:
        """Return leads for an account, optionally filtered by status."""
        stmt = select(Lead).where(Lead.account_id == account_id)
        if status is not None:
            stmt = stmt.where(Lead.status == status)
        stmt = stmt.order_by(Lead.created_at.desc()).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def get_by_comment_id(self, comment_id: str) -> Optional[Lead]:
        """Return a lead by the original comment ID (for deduplication)."""
        stmt = select(Lead).where(Lead.comment_id == comment_id)
        return self.session.execute(stmt).scalars().first()

    def create_lead(
        self,
        account_id: int,
        trigger_id: int,
        commenter_ig_user_id: str,
        commenter_username: str,
        post_instagram_media_id: str,
        comment_id: str,
        comment_text: str,
    ) -> Lead:
        """Create a new Lead record."""
        return self.create(
            account_id=account_id,
            trigger_id=trigger_id,
            commenter_ig_user_id=commenter_ig_user_id,
            commenter_username=commenter_username,
            post_instagram_media_id=post_instagram_media_id,
            comment_id=comment_id,
            comment_text=comment_text,
            conversation_history=[],
            status=LeadStatus.NEW,
        )

    def mark_dm_sent(self, lead_id: int, sent_at: Optional[datetime] = None) -> Optional[Lead]:
        """Mark a lead's initial DM as sent."""
        if sent_at is None:
            sent_at = datetime.now(timezone.utc)
        return self.update(lead_id, dm_sent=True, dm_sent_at=sent_at, status=LeadStatus.CONTACTED)

    def update_conversation(self, lead_id: int, history: list) -> Optional[Lead]:
        """Replace the full conversation_history for a lead."""
        return self.update(lead_id, conversation_history=history)

    def update_status(self, lead_id: int, status: LeadStatus) -> Optional[Lead]:
        """Update the lead's pipeline status."""
        return self.update(lead_id, status=status)

    def get_contacted(self, account_id: int) -> list[Lead]:
        """Return all CONTACTED leads for an account (waiting for replies)."""
        return self.get_by_account(account_id, status=LeadStatus.CONTACTED)
