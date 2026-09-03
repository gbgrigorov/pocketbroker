"""court_check — log of legalacts searches we actually ran

A search that finds no acts writes no ``entity_signal`` row, so signal presence
cannot answer "did we check this company?". This table records the search event
itself (zero-result ones included) and powers the admin inbox's "court checked"
box plus its last-checked date.

Revision ID: a1b2c3d4e5f7
Revises: e5f6a7b8c9d0
Create Date: 2026-08-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'court_check',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('eik', sa.String(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('method', sa.String(), nullable=False, server_default='eik'),
        sa.Column('acts_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_site', sa.String(), nullable=False,
                  server_default='legalacts.justice.bg'),
        sa.Column('checked_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_court_check_eik', 'court_check', ['eik'])


def downgrade() -> None:
    op.drop_index('ix_court_check_eik', table_name='court_check')
    op.drop_table('court_check')
