"""Add exclusion_zones table

Revision ID: 002_exclusion_zones
Revises: 001_initial_models
Create Date: 2025-11-25

Phase D-03: Adds exclusion zones support for marking areas where
assets cannot be placed (wetlands, setbacks, infrastructure buffers, etc.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry


# revision identifiers, used by Alembic.
revision: str = '002_exclusion_zones'
down_revision: Union[str, None] = '001_initial_models'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create exclusion_zones table."""
    
    op.create_table(
        'exclusion_zones',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('zone_type', sa.String(50), nullable=False, default='custom', index=True),
        sa.Column('geometry', Geometry(geometry_type='POLYGON', srid=4326), nullable=False),
        sa.Column('buffer_m', sa.Float(), nullable=False, default=0.0),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('area_m2', sa.Float(), nullable=True),
        sa.Column('site_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('sites.id', ondelete='CASCADE'), 
                  nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), 
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), 
                  server_default=sa.func.now(), nullable=False),
    )
    
    # Create spatial index on geometry
    op.create_index(
        'idx_exclusion_zones_geometry', 
        'exclusion_zones', 
        ['geometry'], 
        postgresql_using='gist',
        if_not_exists=True
    )
    
    # Create composite index for site + zone_type queries
    op.create_index(
        'idx_exclusion_zones_site_type',
        'exclusion_zones',
        ['site_id', 'zone_type'],
        if_not_exists=True
    )


def downgrade() -> None:
    """Drop exclusion_zones table."""
    op.drop_index('idx_exclusion_zones_site_type', table_name='exclusion_zones')
    op.drop_index('idx_exclusion_zones_geometry', table_name='exclusion_zones')
    op.drop_table('exclusion_zones')

