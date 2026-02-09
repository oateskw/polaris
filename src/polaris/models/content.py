"""Content model for posts and captions."""

import enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from polaris.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from polaris.models.account import InstagramAccount
    from polaris.models.schedule import ScheduledPost


class ContentStatus(enum.Enum):
    """Status of content."""

    DRAFT = "draft"
    READY = "ready"
    PUBLISHED = "published"
    FAILED = "failed"


class ContentType(enum.Enum):
    """Type of content."""

    IMAGE = "image"
    VIDEO = "video"
    CAROUSEL = "carousel"
    REEL = "reel"


class Content(Base, TimestampMixin):
    """Content for Instagram posts."""

    __tablename__ = "contents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("instagram_accounts.id"), nullable=False)

    # Content details
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType),
        default=ContentType.IMAGE,
        nullable=False,
    )

    # AI generation metadata
    topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ai_generated: Mapped[bool] = mapped_column(default=False, nullable=False)
    ai_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Status
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus),
        default=ContentStatus.DRAFT,
        nullable=False,
    )

    # Instagram post ID (after publishing)
    instagram_media_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relationships
    account: Mapped["InstagramAccount"] = relationship(
        "InstagramAccount",
        back_populates="contents",
    )
    scheduled_posts: Mapped[list["ScheduledPost"]] = relationship(
        "ScheduledPost",
        back_populates="content",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Content(id={self.id}, status='{self.status.value}')>"

    @property
    def full_caption(self) -> str:
        """Get caption with hashtags appended."""
        if self.hashtags:
            return f"{self.caption}\n\n{self.hashtags}"
        return self.caption
