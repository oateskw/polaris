"""Instagram account model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from polaris.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from polaris.models.analytics import EngagementMetric
    from polaris.models.content import Content
    from polaris.models.schedule import ScheduledPost


class InstagramAccount(Base, TimestampMixin):
    """Instagram account linked to the application."""

    __tablename__ = "instagram_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instagram_user_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # OAuth tokens
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Account metadata
    profile_picture_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    followers_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    following_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    media_count: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    contents: Mapped[list["Content"]] = relationship(
        "Content",
        back_populates="account",
        cascade="all, delete-orphan",
    )
    scheduled_posts: Mapped[list["ScheduledPost"]] = relationship(
        "ScheduledPost",
        back_populates="account",
        cascade="all, delete-orphan",
    )
    engagement_metrics: Mapped[list["EngagementMetric"]] = relationship(
        "EngagementMetric",
        back_populates="account",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<InstagramAccount(id={self.id}, username='{self.username}')>"

    @property
    def is_token_expired(self) -> bool:
        """Check if the access token is expired."""
        if self.token_expires_at is None:
            return False
        return datetime.now(self.token_expires_at.tzinfo) >= self.token_expires_at
