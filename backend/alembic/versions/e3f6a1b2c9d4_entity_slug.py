"""entity slug for SEO-friendly URLs

Adds a cosmetic `entity.slug` column (transliterated from `name`) used to build
human-readable `/e/<eik-or-key>/<slug>` URLs. Not unique and not used for
lookup — eik/person_key/id remain the canonical keys.

Revision ID: e3f6a1b2c9d4
Revises: 775232292fea
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.slugs import slugify


# revision identifiers, used by Alembic.
revision: str = 'e3f6a1b2c9d4'
down_revision: Union[str, Sequence[str], None] = '775232292fea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('entity', sa.Column('slug', sa.Text(), nullable=True))
    conn = op.get_bind()
    entity = sa.table('entity', sa.column('id', sa.Integer), sa.column('name', sa.Text),
                       sa.column('slug', sa.Text))
    for eid, name in conn.execute(sa.select(entity.c.id, entity.c.name)):
        conn.execute(entity.update().where(entity.c.id == eid).values(slug=slugify(name)))


def downgrade() -> None:
    op.drop_column('entity', 'slug')
