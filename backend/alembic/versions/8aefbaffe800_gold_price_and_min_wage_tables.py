"""gold_price and min_wage tables

Revision ID: 8aefbaffe800
Revises: 91b31e26be69
Create Date: 2026-05-30 22:45:02.535478

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8aefbaffe800'
down_revision: Union[str, Sequence[str], None] = '91b31e26be69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'gold_price',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('period_date', sa.Date(), nullable=False),
        sa.Column('price_eur_per_gram', sa.Numeric(), nullable=False),
        sa.Column('source', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('period_date'),
    )
    op.create_table(
        'min_wage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('amount_bgn', sa.Numeric(), nullable=True),
        sa.Column('amount_eur', sa.Numeric(), nullable=True),
        sa.Column('source', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('min_wage')
    op.drop_table('gold_price')
