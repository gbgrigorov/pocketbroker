"""phase 3.5 entity ownership graph

Adds the ownership-graph data model: ``entity`` (companies + persons) and
``entity_edge`` (directed ownership/management connections). Each existing
``builder`` is lifted into the graph as a company entity (``is_builder``) and
linked via ``builder.entity_id``; the now-redundant ``owners``/``managers`` JSON
columns are dropped (connections live as edges instead).

Revision ID: d6354dfd3150
Revises: 3d5c4a6ebfcd
Create Date: 2026-05-31 16:32:37.318464

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from etl.load_phase3 import _norm_name  # pure helper: company-name normalisation


# revision identifiers, used by Alembic.
revision: str = 'd6354dfd3150'
down_revision: Union[str, Sequence[str], None] = '3d5c4a6ebfcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'entity',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('eik', sa.String(), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('name_normalized', sa.Text(), nullable=True),
        sa.Column('person_key', sa.String(), nullable=True),
        sa.Column('is_builder', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('legal_form', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('capital_bgn', sa.Numeric(), nullable=True),
        sa.Column('first_seen', sa.Date(), nullable=True),
        sa.Column('last_seen', sa.Date(), nullable=True),
        sa.Column('source', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_entity_eik'), 'entity', ['eik'], unique=True)
    op.create_index(op.f('ix_entity_name_normalized'), 'entity', ['name_normalized'], unique=False)
    op.create_index(op.f('ix_entity_person_key'), 'entity', ['person_key'], unique=False)

    op.create_table(
        'entity_edge',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('src_entity_id', sa.Integer(), nullable=False),
        sa.Column('dst_entity_id', sa.Integer(), nullable=False),
        sa.Column('relation', sa.String(), nullable=False),
        sa.Column('share_pct', sa.Numeric(), nullable=True),
        sa.Column('role', sa.Text(), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('is_current', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('source', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['src_entity_id'], ['entity.id'], ),
        sa.ForeignKeyConstraint(['dst_entity_id'], ['entity.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('src_entity_id', 'dst_entity_id', 'relation', 'valid_from',
                            name='uq_entity_edge'),
    )
    op.create_index(op.f('ix_entity_edge_src_entity_id'), 'entity_edge', ['src_entity_id'], unique=False)
    op.create_index(op.f('ix_entity_edge_dst_entity_id'), 'entity_edge', ['dst_entity_id'], unique=False)

    op.add_column('builder', sa.Column('entity_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_builder_entity', 'builder', 'entity', ['entity_id'], ['id'])

    # --- Backfill: lift each existing builder into the graph as a company node.
    conn = op.get_bind()
    builders = conn.execute(sa.text(
        "SELECT id, eik, name, legal_form, status, address, capital_bgn FROM builder"
    )).fetchall()
    for b in builders:
        entity_id = conn.execute(sa.text(
            "INSERT INTO entity "
            "(kind, eik, name, name_normalized, is_builder, legal_form, status, "
            " address, capital_bgn, source, created_at) "
            "VALUES ('company', :eik, :name, :nn, true, :lf, :st, :addr, :cap, 'ksb', now()) "
            "RETURNING id"
        ), {
            "eik": b.eik, "name": b.name, "nn": _norm_name(b.name),
            "lf": b.legal_form, "st": b.status, "addr": b.address, "cap": b.capital_bgn,
        }).scalar()
        conn.execute(sa.text("UPDATE builder SET entity_id = :eid WHERE id = :bid"),
                     {"eid": entity_id, "bid": b.id})

    op.drop_column('builder', 'owners')
    op.drop_column('builder', 'managers')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('builder', sa.Column('managers', sa.JSON(), nullable=True))
    op.add_column('builder', sa.Column('owners', sa.JSON(), nullable=True))
    op.drop_constraint('fk_builder_entity', 'builder', type_='foreignkey')
    op.drop_column('builder', 'entity_id')

    op.drop_index(op.f('ix_entity_edge_dst_entity_id'), table_name='entity_edge')
    op.drop_index(op.f('ix_entity_edge_src_entity_id'), table_name='entity_edge')
    op.drop_table('entity_edge')
    op.drop_index(op.f('ix_entity_person_key'), table_name='entity')
    op.drop_index(op.f('ix_entity_name_normalized'), table_name='entity')
    op.drop_index(op.f('ix_entity_eik'), table_name='entity')
    op.drop_table('entity')
