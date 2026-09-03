"""neighbourhood air seasonal aggregate

Adds neighbourhood_air — per-neighbourhood seasonal (winter/summer) air quality
averages, the viz-ready aggregate for the map year slider. Supersedes the
per-sensor air_quality_* tables (retained but unused).

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f6
Create Date: 2026-06-17 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'neighbourhood_air',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('neighbourhood_id', sa.Integer(), sa.ForeignKey('neighbourhood.id'), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('season', sa.String(), nullable=False),
        sa.Column('pm25_avg', sa.Numeric(), nullable=True),
        sa.Column('aqi_avg', sa.Numeric(), nullable=True),
        sa.Column('sensor_count', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('neighbourhood_id', 'year', 'season', name='uq_nbhd_air'),
    )
    op.create_index('ix_neighbourhood_air_neighbourhood_id', 'neighbourhood_air', ['neighbourhood_id'])


def downgrade() -> None:
    op.drop_index('ix_neighbourhood_air_neighbourhood_id', table_name='neighbourhood_air')
    op.drop_table('neighbourhood_air')
