"""entity signal evidence

Adds ``entity_signal`` — the "problematic developer" evidence feed. One row per
public source link (insolvency case, forum complaint, web mention) about a
company OR a person. Strictly an evidence aggregator: every row links to its
source with a date + a match-confidence, never our own verdict.

Revision ID: a1f2c3d4e5f6
Revises: d6354dfd3150
Create Date: 2026-06-01 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd6354dfd3150'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'entity_signal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('subject_kind', sa.String(), nullable=False),
        sa.Column('matched_name', sa.Text(), nullable=False),
        sa.Column('matched_eik', sa.String(), nullable=True),
        sa.Column('matched_person_key', sa.String(), nullable=True),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('tier', sa.String(), nullable=False),
        sa.Column('match_confidence', sa.String(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('snippet', sa.Text(), nullable=True),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('source_site', sa.String(), nullable=True),
        sa.Column('observed_date', sa.Date(), nullable=True),
        sa.Column('scraped_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['entity.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url', 'matched_name', name='uq_entity_signal_url_name'),
    )
    op.create_index(op.f('ix_entity_signal_entity_id'), 'entity_signal', ['entity_id'], unique=False)
    op.create_index(op.f('ix_entity_signal_matched_eik'), 'entity_signal', ['matched_eik'], unique=False)
    op.create_index(op.f('ix_entity_signal_matched_person_key'), 'entity_signal',
                    ['matched_person_key'], unique=False)
    op.create_index(op.f('ix_entity_signal_url'), 'entity_signal', ['url'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_entity_signal_url'), table_name='entity_signal')
    op.drop_index(op.f('ix_entity_signal_matched_person_key'), table_name='entity_signal')
    op.drop_index(op.f('ix_entity_signal_matched_eik'), table_name='entity_signal')
    op.drop_index(op.f('ix_entity_signal_entity_id'), table_name='entity_signal')
    op.drop_table('entity_signal')
