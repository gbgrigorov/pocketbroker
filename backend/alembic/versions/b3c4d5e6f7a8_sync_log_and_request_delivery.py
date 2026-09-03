"""sync_log + research_request delivery fields

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f7
Create Date: 2026-08-20

Adds the delivery record (what we sent back for a request) and the audit log of
every bundle pushed from the research machine.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("research_request", sa.Column("report_md", sa.Text(), nullable=True))
    op.add_column("research_request", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("research_request", sa.Column("delivered_at", sa.DateTime(), nullable=True))

    op.create_table(
        "sync_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(),
                  sa.ForeignKey("research_request.id"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_sync_log_request_id", "sync_log", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_sync_log_request_id", table_name="sync_log")
    op.drop_table("sync_log")
    op.drop_column("research_request", "delivered_at")
    op.drop_column("research_request", "notes")
    op.drop_column("research_request", "report_md")
