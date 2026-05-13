"""Add inbound DM message support to leads table

Revision ID: add_inbound_message_support
Revises: 9c6e4a861330
Create Date: 2026-05-13 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_inbound_message_support'
down_revision: Union[str, None] = '9c6e4a861330'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make comment_id nullable to support inbound DM triggers
    op.alter_column('leads', 'comment_id',
                    existing_type=sa.String(length=100),
                    nullable=True,
                    existing_nullable=False)

    # Add inbound_message_id column for DM-based triggers
    op.add_column('leads', sa.Column('inbound_message_id', sa.String(length=100), nullable=True))

    # Add unique constraint on inbound_message_id
    op.create_unique_constraint('uq_leads_inbound_message_id', 'leads', ['inbound_message_id'])


def downgrade() -> None:
    # Remove unique constraint
    op.drop_constraint('uq_leads_inbound_message_id', 'leads', type_='unique')

    # Remove inbound_message_id column
    op.drop_column('leads', 'inbound_message_id')

    # Revert comment_id to NOT NULL
    op.alter_column('leads', 'comment_id',
                    existing_type=sa.String(length=100),
                    nullable=False,
                    existing_nullable=True)
