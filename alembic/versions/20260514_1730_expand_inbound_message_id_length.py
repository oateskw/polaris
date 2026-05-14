"""Expand inbound_message_id length for Instagram message IDs

Revision ID: 20260514_inbound_len512
Revises: add_inbound_message_support
Create Date: 2026-05-14 17:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260514_inbound_len512"
down_revision: Union[str, None] = "add_inbound_message_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "leads",
        "inbound_message_id",
        existing_type=sa.String(length=100),
        type_=sa.String(length=512),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "leads",
        "inbound_message_id",
        existing_type=sa.String(length=512),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
