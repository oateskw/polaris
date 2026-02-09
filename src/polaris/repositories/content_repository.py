"""Repository for content operations."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from polaris.models.content import Content, ContentStatus, ContentType
from polaris.repositories.base_repository import BaseRepository


class ContentRepository(BaseRepository[Content]):
    """Repository for content CRUD operations."""

    def __init__(self, session: Session):
        super().__init__(session, Content)

    def get_by_account(
        self,
        account_id: int,
        status: Optional[ContentStatus] = None,
        limit: int = 100,
    ) -> list[Content]:
        """Get content for a specific account."""
        stmt = select(Content).where(Content.account_id == account_id)
        if status:
            stmt = stmt.where(Content.status == status)
        stmt = stmt.order_by(Content.created_at.desc()).limit(limit)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_drafts(self, account_id: Optional[int] = None) -> list[Content]:
        """Get all draft content."""
        stmt = select(Content).where(Content.status == ContentStatus.DRAFT)
        if account_id:
            stmt = stmt.where(Content.account_id == account_id)
        stmt = stmt.order_by(Content.created_at.desc())
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_ready_for_publish(self, account_id: Optional[int] = None) -> list[Content]:
        """Get content ready for publishing."""
        stmt = select(Content).where(Content.status == ContentStatus.READY)
        if account_id:
            stmt = stmt.where(Content.account_id == account_id)
        stmt = stmt.order_by(Content.created_at.desc())
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_published(
        self,
        account_id: Optional[int] = None,
        limit: int = 50,
    ) -> list[Content]:
        """Get published content."""
        stmt = select(Content).where(Content.status == ContentStatus.PUBLISHED)
        if account_id:
            stmt = stmt.where(Content.account_id == account_id)
        stmt = stmt.order_by(Content.updated_at.desc()).limit(limit)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def create_content(
        self,
        account_id: int,
        caption: str,
        hashtags: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: ContentType = ContentType.IMAGE,
        topic: Optional[str] = None,
        ai_generated: bool = False,
        ai_model: Optional[str] = None,
    ) -> Content:
        """Create new content."""
        return self.create(
            account_id=account_id,
            caption=caption,
            hashtags=hashtags,
            media_url=media_url,
            media_type=media_type,
            topic=topic,
            ai_generated=ai_generated,
            ai_model=ai_model,
            status=ContentStatus.DRAFT,
        )

    def mark_ready(self, id: int) -> Optional[Content]:
        """Mark content as ready for publishing."""
        return self.update(id, status=ContentStatus.READY)

    def mark_published(
        self,
        id: int,
        instagram_media_id: str,
    ) -> Optional[Content]:
        """Mark content as published."""
        return self.update(
            id,
            status=ContentStatus.PUBLISHED,
            instagram_media_id=instagram_media_id,
        )

    def mark_failed(self, id: int) -> Optional[Content]:
        """Mark content as failed."""
        return self.update(id, status=ContentStatus.FAILED)

    def update_caption(
        self,
        id: int,
        caption: str,
        hashtags: Optional[str] = None,
    ) -> Optional[Content]:
        """Update content caption and hashtags."""
        kwargs = {"caption": caption}
        if hashtags is not None:
            kwargs["hashtags"] = hashtags
        return self.update(id, **kwargs)
