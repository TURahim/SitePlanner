"""Add terrain layout extensions

Revision ID: 004_terrain_layout_extensions
Revises: 003_preferred_layout
Create Date: 2025-11-26

Adds:
- entry_point and entry_point_metadata to sites
- cost_multiplier to exclusion_zones
- road_class, parent_segment_id, KPI fields to roads
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = '004_terrain_layout_extensions'
down_revision: Union[str, None] = '003_preferred_layout'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add entry_point and metadata to sites
    op.add_column(
        'sites',
        sa.Column(
            'entry_point',
            Geometry(geometry_type='POINT', srid=4326),
            nullable=True
        )
    )
    op.add_column(
        'sites',
        sa.Column(
            'entry_point_metadata',
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True
        )
    )

    # Add cost_multiplier to exclusion_zones
    op.add_column(
        'exclusion_zones',
        sa.Column(
            'cost_multiplier',
            sa.Float(),
            server_default='1.0',
            nullable=False
        )
    )

    # Add fields to roads
    op.add_column(
        'roads',
        sa.Column('road_class', sa.String(length=50), nullable=True)
    )
    op.add_column(
        'roads',
        sa.Column(
            'parent_segment_id',
            postgresql.UUID(as_uuid=True),
            nullable=True
        )
    )
    op.create_foreign_key(
        'fk_roads_parent_segment_id_roads',
        'roads', 'roads',
        ['parent_segment_id'], ['id'],
        ondelete='SET NULL'
    )
    
    op.add_column('roads', sa.Column('avg_grade_pct', sa.Float(), nullable=True))
    op.add_column('roads', sa.Column('max_cumulative_cost', sa.Float(), nullable=True))
    op.add_column('roads', sa.Column('kpi_flags', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('roads', sa.Column('stationing_json', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Drop fields from roads
    op.drop_column('roads', 'stationing_json')
    op.drop_column('roads', 'kpi_flags')
    op.drop_column('roads', 'max_cumulative_cost')
    op.drop_column('roads', 'avg_grade_pct')
    op.drop_constraint('fk_roads_parent_segment_id_roads', 'roads', type_='foreignkey')
    op.drop_column('roads', 'parent_segment_id')
    op.drop_column('roads', 'road_class')

    # Drop cost_multiplier from exclusion_zones
    op.drop_column('exclusion_zones', 'cost_multiplier')

    # Drop entry_point fields from sites
    op.drop_column('sites', 'entry_point_metadata')
    op.drop_column('sites', 'entry_point')

