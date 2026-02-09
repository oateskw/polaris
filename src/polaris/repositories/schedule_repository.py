"""Repository for scheduled post operations."""

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from polaris.models.schedule import ScheduledPost, ScheduleStatus
from polaris.repositories.base_repository import BaseRepository


class ScheduleRepository(BaseRepository[ScheduledPost]):
    """Repository for scheduled post CRUD operations."""

    def __init__(self, session: Session):
        super().__init__(session, ScheduledPost)

    def get_by_account(
        self,
        account_id: int,
        status: Optional[ScheduleStatus] = None,
        limit: int = 100,
    ) -> list[ScheduledPost]:
        """Get scheduled posts for a specific account."""
        stmt = select(ScheduledPost).where(ScheduledPost.account_id == account_id)
        if status:
            stmt = stmt.where(ScheduledPost.status == status)
        stmt = stmt.order_by(ScheduledPost.scheduled_time.asc()).limit(limit)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_pending(self, account_id: Optional[int] = None) -> list[ScheduledPost]:
        """Get all pending scheduled posts."""
        stmt = select(ScheduledPost).where(ScheduledPost.status == ScheduleStatus.PENDING)
        if account_id:
            stmt = stmt.where(ScheduledPost.account_id == account_id)
        stmt = stmt.order_by(ScheduledPost.scheduled_time.asc())
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_upcoming(
        self,
        account_id: Optional[int] = None,
        hours: int = 24,
    ) -> list[ScheduledPost]:
        """Get posts scheduled within the next N hours."""
        from datetime import timedelta, timezone

        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=hours)

        stmt = select(ScheduledPost).where(
            and_(
                ScheduledPost.status == ScheduleStatus.PENDING,
                ScheduledPost.scheduled_time >= now,
                ScheduledPost.scheduled_time <= end,
            )
        )
        if account_id:
            stmt = stmt.where(ScheduledPost.account_id == account_id)
        stmt = stmt.order_by(ScheduledPost.scheduled_time.asc())
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_failed(self, account_id: Optional[int] = None) -> list[ScheduledPost]:
        """Get failed scheduled posts."""
        stmt = select(ScheduledPost).where(ScheduledPost.status == ScheduleStatus.FAILED)
        if account_id:
            stmt = stmt.where(ScheduledPost.account_id == account_id)
        stmt = stmt.order_by(ScheduledPost.scheduled_time.desc())
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_by_job_id(self, job_id: str) -> Optional[ScheduledPost]:
        """Get scheduled post by APScheduler job ID."""
        stmt = select(ScheduledPost).where(ScheduledPost.job_id == job_id)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def create_scheduled_post(
        self,
        account_id: int,
        content_id: int,
        scheduled_time: datetime,
        job_id: Optional[str] = None,
    ) -> ScheduledPost:
        """Create a new scheduled post."""
        return self.create(
            account_id=account_id,
            content_id=content_id,
            scheduled_time=scheduled_time,
            job_id=job_id,
            status=ScheduleStatus.PENDING,
        )

    def update_job_id(self, id: int, job_id: str) -> Optional[ScheduledPost]:
        """Update the APScheduler job ID."""
        return self.update(id, job_id=job_id)

    def mark_processing(self, id: int) -> Optional[ScheduledPost]:
        """Mark scheduled post as processing."""
        return self.update(id, status=ScheduleStatus.PROCESSING)

    def mark_published(self, id: int) -> Optional[ScheduledPost]:
        """Mark scheduled post as published."""
        from datetime import timezone

        return self.update(
            id,
            status=ScheduleStatus.PUBLISHED,
            published_at=datetime.now(timezone.utc),
        )

    def mark_failed(self, id: int, error_message: str) -> Optional[ScheduledPost]:
        """Mark scheduled post as failed."""
        post = self.get(id)
        if post:
            return self.update(
                id,
                status=ScheduleStatus.FAILED,
                error_message=error_message,
                retry_count=post.retry_count + 1,
            )
        return None

    def mark_cancelled(self, id: int) -> Optional[ScheduledPost]:
        """Cancel a scheduled post."""
        return self.update(id, status=ScheduleStatus.CANCELLED)

    def reschedule(self, id: int, new_time: datetime) -> Optional[ScheduledPost]:
        """Reschedule a post to a new time."""
        return self.update(
            id,
            scheduled_time=new_time,
            status=ScheduleStatus.PENDING,
        )
