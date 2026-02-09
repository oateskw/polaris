"""Post scheduling service using APScheduler."""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.orm import Session

from polaris.config import Settings, get_settings
from polaris.models.content import Content, ContentStatus
from polaris.models.schedule import ScheduledPost, ScheduleStatus
from polaris.services.instagram.client import InstagramClient
from polaris.services.instagram.publisher import InstagramPublisher

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for scheduling Instagram posts."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.session_factory = session_factory
        self._scheduler: Optional[BackgroundScheduler] = None

    def _get_scheduler(self) -> BackgroundScheduler:
        """Get or create the scheduler instance."""
        if self._scheduler is None:
            jobstores = {
                "default": SQLAlchemyJobStore(url=self.settings.database_url)
            }

            self._scheduler = BackgroundScheduler(
                jobstores=jobstores,
                job_defaults={
                    "coalesce": True,
                    "max_instances": 1,
                    "misfire_grace_time": 3600,  # 1 hour grace period
                },
            )

            # Add event listeners
            self._scheduler.add_listener(
                self._on_job_executed,
                EVENT_JOB_EXECUTED,
            )
            self._scheduler.add_listener(
                self._on_job_error,
                EVENT_JOB_ERROR,
            )

        return self._scheduler

    def start(self) -> None:
        """Start the scheduler."""
        scheduler = self._get_scheduler()
        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")

    def schedule_post(
        self,
        scheduled_post_id: int,
        scheduled_time: datetime,
    ) -> str:
        """Schedule a post for publishing.

        Args:
            scheduled_post_id: ID of the ScheduledPost record
            scheduled_time: When to publish the post

        Returns:
            Job ID
        """
        scheduler = self._get_scheduler()

        # Ensure timezone awareness
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)

        job = scheduler.add_job(
            self._publish_scheduled_post,
            trigger=DateTrigger(run_date=scheduled_time),
            args=[scheduled_post_id],
            id=f"scheduled_post_{scheduled_post_id}",
            replace_existing=True,
        )

        logger.info(f"Scheduled post {scheduled_post_id} for {scheduled_time}")
        return job.id

    def cancel_scheduled_post(self, job_id: str) -> bool:
        """Cancel a scheduled post.

        Args:
            job_id: The APScheduler job ID

        Returns:
            True if cancelled, False if not found
        """
        scheduler = self._get_scheduler()
        try:
            scheduler.remove_job(job_id)
            logger.info(f"Cancelled job {job_id}")
            return True
        except Exception:
            return False

    def reschedule_post(
        self,
        job_id: str,
        new_time: datetime,
    ) -> bool:
        """Reschedule a post to a new time.

        Args:
            job_id: The APScheduler job ID
            new_time: New scheduled time

        Returns:
            True if rescheduled, False if not found
        """
        scheduler = self._get_scheduler()

        if new_time.tzinfo is None:
            new_time = new_time.replace(tzinfo=timezone.utc)

        try:
            scheduler.reschedule_job(
                job_id,
                trigger=DateTrigger(run_date=new_time),
            )
            logger.info(f"Rescheduled job {job_id} to {new_time}")
            return True
        except Exception:
            return False

    def _publish_scheduled_post(self, scheduled_post_id: int) -> None:
        """Execute the scheduled post publishing.

        This is called by APScheduler when the scheduled time arrives.
        """
        session = self.session_factory()
        try:
            # Get the scheduled post
            scheduled_post = session.get(ScheduledPost, scheduled_post_id)
            if not scheduled_post:
                logger.error(f"Scheduled post {scheduled_post_id} not found")
                return

            if scheduled_post.status != ScheduleStatus.PENDING:
                logger.info(f"Scheduled post {scheduled_post_id} already processed")
                return

            # Update status to processing
            scheduled_post.status = ScheduleStatus.PROCESSING
            session.commit()

            # Get the content and account
            content = scheduled_post.content
            account = scheduled_post.account

            if not account.is_active:
                raise Exception("Account is not active")

            if account.is_token_expired:
                raise Exception("Account token is expired")

            # Create client and publisher
            client = InstagramClient(
                access_token=account.access_token,
                instagram_user_id=account.instagram_user_id,
            )
            publisher = InstagramPublisher(client)

            # Publish the content
            media_id = publisher.publish_content(content)

            # Update records
            content.status = ContentStatus.PUBLISHED
            content.instagram_media_id = media_id
            scheduled_post.status = ScheduleStatus.PUBLISHED
            scheduled_post.published_at = datetime.now(timezone.utc)

            session.commit()
            logger.info(f"Successfully published scheduled post {scheduled_post_id}")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to publish scheduled post {scheduled_post_id}: {e}")

            # Update with error
            scheduled_post = session.get(ScheduledPost, scheduled_post_id)
            if scheduled_post:
                scheduled_post.status = ScheduleStatus.FAILED
                scheduled_post.error_message = str(e)
                scheduled_post.retry_count += 1

                # Schedule retry if possible
                if scheduled_post.can_retry:
                    retry_time = datetime.now(timezone.utc)
                    retry_time = retry_time.replace(
                        minute=retry_time.minute + (5 * scheduled_post.retry_count)
                    )
                    scheduled_post.status = ScheduleStatus.PENDING
                    session.commit()
                    self.schedule_post(scheduled_post_id, retry_time)
                else:
                    session.commit()

        finally:
            session.close()

    def _on_job_executed(self, event: JobExecutionEvent) -> None:
        """Handle successful job execution."""
        logger.debug(f"Job {event.job_id} executed successfully")

    def _on_job_error(self, event: JobExecutionEvent) -> None:
        """Handle job execution error."""
        logger.error(f"Job {event.job_id} failed: {event.exception}")

    def get_pending_jobs(self) -> list[dict]:
        """Get list of pending scheduled jobs."""
        scheduler = self._get_scheduler()
        jobs = scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "next_run_time": job.next_run_time,
                "name": job.name,
            }
            for job in jobs
        ]
