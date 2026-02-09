"""Repository for analytics and engagement metrics."""

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from polaris.models.analytics import EngagementMetric
from polaris.repositories.base_repository import BaseRepository


class AnalyticsRepository(BaseRepository[EngagementMetric]):
    """Repository for engagement metric CRUD operations."""

    def __init__(self, session: Session):
        super().__init__(session, EngagementMetric)

    def get_by_media_id(
        self,
        instagram_media_id: str,
        latest_only: bool = True,
    ) -> list[EngagementMetric]:
        """Get metrics for a specific media post."""
        stmt = select(EngagementMetric).where(
            EngagementMetric.instagram_media_id == instagram_media_id
        )
        stmt = stmt.order_by(EngagementMetric.recorded_at.desc())
        if latest_only:
            stmt = stmt.limit(1)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_by_account(
        self,
        account_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[EngagementMetric]:
        """Get metrics for an account within a date range."""
        stmt = select(EngagementMetric).where(
            EngagementMetric.account_id == account_id
        )
        if start_date:
            stmt = stmt.where(EngagementMetric.recorded_at >= start_date)
        if end_date:
            stmt = stmt.where(EngagementMetric.recorded_at <= end_date)
        stmt = stmt.order_by(EngagementMetric.recorded_at.desc()).limit(limit)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def record_metric(
        self,
        account_id: int,
        instagram_media_id: str,
        recorded_at: datetime,
        impressions: Optional[int] = None,
        reach: Optional[int] = None,
        likes: Optional[int] = None,
        comments: Optional[int] = None,
        shares: Optional[int] = None,
        saves: Optional[int] = None,
        video_views: Optional[int] = None,
    ) -> EngagementMetric:
        """Record a new engagement metric snapshot."""
        return self.create(
            account_id=account_id,
            instagram_media_id=instagram_media_id,
            recorded_at=recorded_at,
            impressions=impressions,
            reach=reach,
            likes=likes,
            comments=comments,
            shares=shares,
            saves=saves,
            video_views=video_views,
        )

    def get_account_totals(
        self,
        account_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """Get aggregated totals for an account."""
        stmt = select(
            func.sum(EngagementMetric.impressions).label("total_impressions"),
            func.sum(EngagementMetric.reach).label("total_reach"),
            func.sum(EngagementMetric.likes).label("total_likes"),
            func.sum(EngagementMetric.comments).label("total_comments"),
            func.sum(EngagementMetric.shares).label("total_shares"),
            func.sum(EngagementMetric.saves).label("total_saves"),
            func.count(EngagementMetric.id).label("post_count"),
        ).where(EngagementMetric.account_id == account_id)

        if start_date:
            stmt = stmt.where(EngagementMetric.recorded_at >= start_date)
        if end_date:
            stmt = stmt.where(EngagementMetric.recorded_at <= end_date)

        result = self.session.execute(stmt).first()

        return {
            "total_impressions": result.total_impressions or 0,
            "total_reach": result.total_reach or 0,
            "total_likes": result.total_likes or 0,
            "total_comments": result.total_comments or 0,
            "total_shares": result.total_shares or 0,
            "total_saves": result.total_saves or 0,
            "post_count": result.post_count or 0,
        }

    def get_top_performing_posts(
        self,
        account_id: int,
        metric: str = "likes",
        limit: int = 10,
    ) -> list[EngagementMetric]:
        """Get top performing posts by a specific metric."""
        # Get the latest metric for each media_id
        subquery = (
            select(
                EngagementMetric.instagram_media_id,
                func.max(EngagementMetric.recorded_at).label("max_recorded"),
            )
            .where(EngagementMetric.account_id == account_id)
            .group_by(EngagementMetric.instagram_media_id)
            .subquery()
        )

        stmt = (
            select(EngagementMetric)
            .join(
                subquery,
                and_(
                    EngagementMetric.instagram_media_id == subquery.c.instagram_media_id,
                    EngagementMetric.recorded_at == subquery.c.max_recorded,
                ),
            )
            .where(EngagementMetric.account_id == account_id)
        )

        # Order by the specified metric
        metric_column = getattr(EngagementMetric, metric, EngagementMetric.likes)
        stmt = stmt.order_by(metric_column.desc()).limit(limit)

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_average_engagement(
        self,
        account_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """Calculate average engagement metrics for an account."""
        stmt = select(
            func.avg(EngagementMetric.impressions).label("avg_impressions"),
            func.avg(EngagementMetric.reach).label("avg_reach"),
            func.avg(EngagementMetric.likes).label("avg_likes"),
            func.avg(EngagementMetric.comments).label("avg_comments"),
            func.avg(EngagementMetric.shares).label("avg_shares"),
            func.avg(EngagementMetric.saves).label("avg_saves"),
        ).where(EngagementMetric.account_id == account_id)

        if start_date:
            stmt = stmt.where(EngagementMetric.recorded_at >= start_date)
        if end_date:
            stmt = stmt.where(EngagementMetric.recorded_at <= end_date)

        result = self.session.execute(stmt).first()

        return {
            "avg_impressions": round(result.avg_impressions or 0, 2),
            "avg_reach": round(result.avg_reach or 0, 2),
            "avg_likes": round(result.avg_likes or 0, 2),
            "avg_comments": round(result.avg_comments or 0, 2),
            "avg_shares": round(result.avg_shares or 0, 2),
            "avg_saves": round(result.avg_saves or 0, 2),
        }
