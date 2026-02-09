"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create instagram_accounts table
    op.create_table(
        "instagram_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instagram_user_id", sa.String(50), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profile_picture_url", sa.Text(), nullable=True),
        sa.Column("followers_count", sa.Integer(), nullable=True),
        sa.Column("following_count", sa.Integer(), nullable=True),
        sa.Column("media_count", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instagram_user_id"),
    )

    # Create contents table
    op.create_table(
        "contents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("hashtags", sa.Text(), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column(
            "media_type",
            sa.Enum("IMAGE", "VIDEO", "CAROUSEL", "REEL", name="contenttype"),
            nullable=False,
            default="IMAGE",
        ),
        sa.Column("topic", sa.String(255), nullable=True),
        sa.Column("ai_generated", sa.Boolean(), nullable=False, default=False),
        sa.Column("ai_model", sa.String(50), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "READY", "PUBLISHED", "FAILED", name="contentstatus"),
            nullable=False,
            default="DRAFT",
        ),
        sa.Column("instagram_media_id", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"]),
    )

    # Create scheduled_posts table
    op.create_table(
        "scheduled_posts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "PROCESSING", "PUBLISHED", "FAILED", "CANCELLED",
                name="schedulestatus"
            ),
            nullable=False,
            default="PENDING",
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, default=0),
        sa.Column("max_retries", sa.Integer(), nullable=False, default=3),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"]),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"]),
    )

    # Create engagement_metrics table
    op.create_table(
        "engagement_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("instagram_media_id", sa.String(50), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=True),
        sa.Column("reach", sa.Integer(), nullable=True),
        sa.Column("likes", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("shares", sa.Integer(), nullable=True),
        sa.Column("saves", sa.Integer(), nullable=True),
        sa.Column("video_views", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"]),
    )

    # Create indexes
    op.create_index("ix_contents_account_id", "contents", ["account_id"])
    op.create_index("ix_contents_status", "contents", ["status"])
    op.create_index("ix_scheduled_posts_account_id", "scheduled_posts", ["account_id"])
    op.create_index("ix_scheduled_posts_status", "scheduled_posts", ["status"])
    op.create_index("ix_scheduled_posts_scheduled_time", "scheduled_posts", ["scheduled_time"])
    op.create_index("ix_engagement_metrics_account_id", "engagement_metrics", ["account_id"])
    op.create_index("ix_engagement_metrics_media_id", "engagement_metrics", ["instagram_media_id"])
    op.create_index("ix_engagement_metrics_recorded_at", "engagement_metrics", ["recorded_at"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_engagement_metrics_recorded_at", "engagement_metrics")
    op.drop_index("ix_engagement_metrics_media_id", "engagement_metrics")
    op.drop_index("ix_engagement_metrics_account_id", "engagement_metrics")
    op.drop_index("ix_scheduled_posts_scheduled_time", "scheduled_posts")
    op.drop_index("ix_scheduled_posts_status", "scheduled_posts")
    op.drop_index("ix_scheduled_posts_account_id", "scheduled_posts")
    op.drop_index("ix_contents_status", "contents")
    op.drop_index("ix_contents_account_id", "contents")

    # Drop tables
    op.drop_table("engagement_metrics")
    op.drop_table("scheduled_posts")
    op.drop_table("contents")
    op.drop_table("instagram_accounts")

    # Drop enums (for PostgreSQL)
    op.execute("DROP TYPE IF EXISTS schedulestatus")
    op.execute("DROP TYPE IF EXISTS contentstatus")
    op.execute("DROP TYPE IF EXISTS contenttype")
