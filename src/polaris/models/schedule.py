"""Scheduled post model."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from polaris.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from polaris.models.account import InstagramAccount
    from polaris.models.content import Content


class ScheduleStatus(enum.Enum):
    """Status of scheduled post."""

    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduledPost(Base, TimestampMixin):
    """Scheduled Instagram post."""

    __tablename__ = "scheduled_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("instagram_accounts.id"), nullable=False)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"), nullable=False)

    # Schedule details
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ScheduleStatus] = mapped_column(
        Enum(ScheduleStatus),
        default=ScheduleStatus.PENDING,
        nullable=False,
    )

    # Execution details
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(default=3, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # APScheduler job ID
    job_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    account: Mapped["InstagramAccount"] = relationship(
        "InstagramAccount",
        back_populates="scheduled_posts",
    )
    content: Mapped["Content"] = relationship(
        "Content",
        back_populates="scheduled_posts",
    )

    def __repr__(self) -> str:
        return f"<ScheduledPost(id={self.id}, status='{self.status.value}')>"

    @property
    def can_retry(self) -> bool:
        """Check if the post can be retried."""
        return self.retry_count < self.max_retries and self.status == ScheduleStatus.FAILED
