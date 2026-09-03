"""air quality tables

Adds air_quality_station, air_quality_snapshot, neighbourhood_air_station
for the AQI / PM2.5 bubble-map metrics.

Revision ID: a1b2c3d4e5f6
Revises: c7d8e9f0a1b2
Create Date: 2026-06-17 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'air_quality_station',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('city_id', sa.Integer(), sa.ForeignKey('city.id'), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('lat', sa.Numeric(9, 7), nullable=True),
        sa.Column('lon', sa.Numeric(9, 7), nullable=True),
        sa.Column('external_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'air_quality_snapshot',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('station_id', sa.Integer(), sa.ForeignKey('air_quality_station.id'), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('pm25_annual_avg', sa.Numeric(), nullable=True),
        sa.Column('aqi_annual_avg', sa.Numeric(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('station_id', 'year', name='uq_aq_station_year'),
    )
    op.create_table(
        'neighbourhood_air_station',
        sa.Column('neighbourhood_id', sa.Integer(), sa.ForeignKey('neighbourhood.id'), nullable=False),
        sa.Column('station_id', sa.Integer(), sa.ForeignKey('air_quality_station.id'), nullable=False),
        sa.Column('distance_m', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('neighbourhood_id', 'station_id'),
    )


def downgrade() -> None:
    op.drop_table('neighbourhood_air_station')
    op.drop_table('air_quality_snapshot')
    op.drop_table('air_quality_station')
