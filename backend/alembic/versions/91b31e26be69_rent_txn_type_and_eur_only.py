"""rent txn type and eur only

Revision ID: 91b31e26be69
Revises: 2575703c0c0e
Create Date: 2026-05-30 22:38:21.662555

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91b31e26be69'
down_revision: Union[str, Sequence[str], None] = '2575703c0c0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('price_snapshot', sa.Column('transaction_type', sa.Text(), nullable=True))
    op.execute("UPDATE price_snapshot SET transaction_type = 'sale' WHERE transaction_type IS NULL")
    op.create_index('ix_price_snapshot_nbhd_txn_period', 'price_snapshot',
                    ['neighbourhood_id', 'transaction_type', 'period_date'])
    op.drop_column('price_snapshot', 'price_bgn')
    op.drop_column('price_snapshot', 'price_bgn_sqm')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('price_snapshot', sa.Column('price_bgn_sqm', sa.Numeric(), nullable=True))
    op.add_column('price_snapshot', sa.Column('price_bgn', sa.Numeric(), nullable=True))
    op.drop_index('ix_price_snapshot_nbhd_txn_period', table_name='price_snapshot')
    op.drop_column('price_snapshot', 'transaction_type')
