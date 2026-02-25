"""Lead management models for comment-to-DM automation."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from polaris.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from polaris.models.account import InstagramAccount


class LeadStatus(str, enum.Enum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    REPLIED = "REPLIED"
    QUALIFIED = "QUALIFIED"
    CLOSED = "CLOSED"


class CommentTrigger(Base, TimestampMixin):
    """Watches an Instagram post for comments matching a keyword."""

    __tablename__ = "comment_triggers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("instagram_accounts.id"), nullable=False)
    post_instagram_media_id: Mapped[str] = mapped_column(String(100), nullable=False)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    initial_message: Mapped[str] = mapped_column(Text, nullable=False)
    follow_up_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    account: Mapped["InstagramAccount"] = relationship("InstagramAccount")
    leads: Mapped[list["Lead"]] = relationship(
        "Lead",
        back_populates="trigger",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<CommentTrigger(id={self.id}, keyword='{self.keyword}', post='{self.post_instagram_media_id}')>"


class Lead(Base, TimestampMixin):
    """A lead captured from a comment trigger."""

    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("comment_id", name="uq_leads_comment_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("instagram_accounts.id"), nullable=False)
    trigger_id: Mapped[int] = mapped_column(ForeignKey("comment_triggers.id"), nullable=False)
    commenter_ig_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    commenter_username: Mapped[str] = mapped_column(String(100), nullable=False)
    post_instagram_media_id: Mapped[str] = mapped_column(String(100), nullable=False)
    comment_id: Mapped[str] = mapped_column(String(100), nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    dm_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dm_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    conversation_history: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus),
        default=LeadStatus.NEW,
        nullable=False,
    )

    # Relationships
    account: Mapped["InstagramAccount"] = relationship("InstagramAccount")
    trigger: Mapped["CommentTrigger"] = relationship("CommentTrigger", back_populates="leads")

    def __repr__(self) -> str:
        return f"<Lead(id={self.id}, username='{self.commenter_username}', status='{self.status}')>"
