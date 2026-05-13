"""Model for tracking comments we have already replied to."""

from typing import Optional
from datetime import datetime

from sqlalchemy import ForeignKey, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from polaris.models.base import Base, TimestampMixin


class CommentReply(Base, TimestampMixin):
    """Records every public comment reply Polaris has posted.

    Used for deduplication so we never reply to the same comment twice.
    """

    __tablename__ = "comment_replies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("instagram_accounts.id"), nullable=False)
    post_media_id: Mapped[str] = mapped_column(String(64), nullable=False)
    comment_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    commenter_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    comment_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    reply_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    replied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
