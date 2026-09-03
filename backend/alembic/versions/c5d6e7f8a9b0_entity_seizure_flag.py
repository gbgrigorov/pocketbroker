"""entity seizure flag (запор върху дружествен дял)

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-08-20

A запор is an attachment on a partner's share, registered in the Търговски
регистър by a creditor enforcing against that partner personally. It never
appears in legalacts.justice.bg, because enforcement runs before a частен
съдебен изпълнител rather than a court — so a company under active enforcement
reads as clean in the court portal and in third-party aggregators.

Additive and non-destructive: four nullable/defaulted columns on ``entity``.
Existing rows default to has_seizure = false, seizure_count = 0, which is
"not known to have one" rather than "confirmed clean" — nothing in the graph
has been checked for a запор yet.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("entity", sa.Column("has_seizure", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    op.add_column("entity", sa.Column("seizure_count", sa.Integer(), nullable=False,
                                      server_default="0"))
    op.add_column("entity", sa.Column("seizure_last_at", sa.Date(), nullable=True))
    op.add_column("entity", sa.Column("seizure_source_url", sa.Text(), nullable=True))
    # Partial index: the flagged rows are a tiny minority and are what gets filtered on.
    op.create_index("ix_entity_has_seizure", "entity", ["has_seizure"],
                    postgresql_where=sa.text("has_seizure"))


def downgrade() -> None:
    op.drop_index("ix_entity_has_seizure", table_name="entity")
    op.drop_column("entity", "seizure_source_url")
    op.drop_column("entity", "seizure_last_at")
    op.drop_column("entity", "seizure_count")
    op.drop_column("entity", "has_seizure")
