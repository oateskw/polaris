"""Analytics and engagement metrics model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from polaris.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from polaris.models.account import InstagramAccount


class EngagementMetric(Base, TimestampMixin):
    """Engagement metrics for Instagram posts."""

    __tablename__ = "engagement_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("instagram_accounts.id"), nullable=False)

    # Instagram media reference
    instagram_media_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # Metrics snapshot
    impressions: Mapped[Optional[int]] = mapped_column(nullable=True)
    reach: Mapped[Optional[int]] = mapped_column(nullable=True)
    likes: Mapped[Optional[int]] = mapped_column(nullable=True)
    comments: Mapped[Optional[int]] = mapped_column(nullable=True)
    shares: Mapped[Optional[int]] = mapped_column(nullable=True)
    saves: Mapped[Optional[int]] = mapped_column(nullable=True)
    video_views: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Snapshot timestamp
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    account: Mapped["InstagramAccount"] = relationship(
        "InstagramAccount",
        back_populates="engagement_metrics",
    )

    def __repr__(self) -> str:
        return f"<EngagementMetric(id={self.id}, media_id='{self.instagram_media_id}')>"

    @property
    def engagement_rate(self) -> Optional[float]:
        """Calculate engagement rate based on available metrics."""
        if self.reach and self.reach > 0:
            total_engagement = (self.likes or 0) + (self.comments or 0) + (self.shares or 0)
            return (total_engagement / self.reach) * 100
        return None

    @property
    def total_interactions(self) -> int:
        """Get total number of interactions."""
        return (
            (self.likes or 0)
            + (self.comments or 0)
            + (self.shares or 0)
            + (self.saves or 0)
        )
