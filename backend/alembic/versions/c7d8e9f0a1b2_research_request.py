"""research request lead capture

Adds ``research_request`` — visitor-submitted "order a research" requests from the
empty state of the builder/company search. Public form (login optional); ``user_id``
is set only when the submitter happened to be logged in. ``status`` defaults to
``'new'`` as the seam for a future triage view.

Revision ID: c7d8e9f0a1b2
Revises: f1a2b3c4d5e6
Create Date: 2026-06-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'research_request',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_name', sa.Text(), nullable=False),
        sa.Column('company_eik', sa.String(), nullable=True),
        sa.Column('owner', sa.Text(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('requester_name', sa.Text(), nullable=True),
        sa.Column('requester_email', sa.String(), nullable=False),
        sa.Column('search_query', sa.String(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), server_default='new', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_research_request_user_id'), 'research_request', ['user_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_research_request_user_id'), table_name='research_request')
    op.drop_table('research_request')
