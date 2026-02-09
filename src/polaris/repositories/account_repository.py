"""Repository for Instagram account operations."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from polaris.models.account import InstagramAccount
from polaris.repositories.base_repository import BaseRepository


class AccountRepository(BaseRepository[InstagramAccount]):
    """Repository for Instagram account CRUD operations."""

    def __init__(self, session: Session):
        super().__init__(session, InstagramAccount)

    def get_by_instagram_id(self, instagram_user_id: str) -> Optional[InstagramAccount]:
        """Get account by Instagram user ID."""
        stmt = select(InstagramAccount).where(
            InstagramAccount.instagram_user_id == instagram_user_id
        )
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def get_by_username(self, username: str) -> Optional[InstagramAccount]:
        """Get account by username."""
        stmt = select(InstagramAccount).where(InstagramAccount.username == username)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def get_active_accounts(self) -> list[InstagramAccount]:
        """Get all active accounts."""
        stmt = select(InstagramAccount).where(InstagramAccount.is_active == True)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def deactivate(self, id: int) -> Optional[InstagramAccount]:
        """Deactivate an account."""
        return self.update(id, is_active=False)

    def activate(self, id: int) -> Optional[InstagramAccount]:
        """Activate an account."""
        return self.update(id, is_active=True)

    def update_token(
        self,
        id: int,
        access_token: str,
        token_expires_at=None,
    ) -> Optional[InstagramAccount]:
        """Update account access token."""
        return self.update(
            id,
            access_token=access_token,
            token_expires_at=token_expires_at,
        )

    def update_metrics(
        self,
        id: int,
        followers_count: Optional[int] = None,
        following_count: Optional[int] = None,
        media_count: Optional[int] = None,
    ) -> Optional[InstagramAccount]:
        """Update account metrics."""
        kwargs = {}
        if followers_count is not None:
            kwargs["followers_count"] = followers_count
        if following_count is not None:
            kwargs["following_count"] = following_count
        if media_count is not None:
            kwargs["media_count"] = media_count

        if kwargs:
            return self.update(id, **kwargs)
        return self.get(id)
