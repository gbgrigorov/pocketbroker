"""court / deep-research order fields on research_request

Court-research orders share the ``research_request`` inbox with plain leads.
``order_type`` discriminates them; the rest carry the quote we computed
(see ``app.pricing``). All additive + nullable (or server-defaulted), so existing
lead rows stay valid.

Revision ID: d4e5f6a7b8c9
Revises: c4d5e6f7a8b9
Create Date: 2026-06-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('research_request',
                  sa.Column('order_type', sa.String(), server_default='lead', nullable=False))
    op.add_column('research_request', sa.Column('scope', sa.String(), nullable=True))
    op.add_column('research_request', sa.Column('search_type', sa.String(), nullable=True))
    op.add_column('research_request', sa.Column('network_depth', sa.Integer(), nullable=True))
    op.add_column('research_request', sa.Column('entity_count', sa.Integer(), nullable=True))
    op.add_column('research_request', sa.Column('price_eur', sa.Numeric(), nullable=True))
    op.add_column('research_request',
                  sa.Column('expedited', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('research_request', 'expedited')
    op.drop_column('research_request', 'price_eur')
    op.drop_column('research_request', 'entity_count')
    op.drop_column('research_request', 'network_depth')
    op.drop_column('research_request', 'search_type')
    op.drop_column('research_request', 'scope')
    op.drop_column('research_request', 'order_type')
