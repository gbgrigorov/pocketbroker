"""neighbourhood slug unique per city, not globally

imot.bg reuses neighbourhood slugs across cities (every city has a "tsentar",
Varna & Burgas both have "lazur", …). Replace the global UNIQUE(slug) with a
composite UNIQUE(city_id, slug) so multi-city data can coexist.

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5f6
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1f2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("neighbourhood_slug_key", "neighbourhood", type_="unique")
    op.create_unique_constraint(
        "uq_neighbourhood_city_slug", "neighbourhood", ["city_id", "slug"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_neighbourhood_city_slug", "neighbourhood", type_="unique")
    op.create_unique_constraint(
        "neighbourhood_slug_key", "neighbourhood", ["slug"]
    )
