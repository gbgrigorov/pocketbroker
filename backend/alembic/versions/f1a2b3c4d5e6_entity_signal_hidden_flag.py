"""entity signal hidden flag

Adds ``entity_signal.hidden`` (default false) — a per-record on/off switch
for the "Reports & records" evidence feed. When true, the signal is excluded
from display everywhere (its own entity page, sibling rollups, list counts),
without deleting the underlying evidence row.

Revision ID: f1a2b3c4d5e6
Revises: e3f6a1b2c9d4
Create Date: 2026-06-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e3f6a1b2c9d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'entity_signal',
        sa.Column('hidden', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('entity_signal', 'hidden')
