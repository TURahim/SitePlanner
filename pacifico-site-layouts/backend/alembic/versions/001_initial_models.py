"""Initial database models

Revision ID: 001_initial_models
Revises: 
Create Date: 2025-11-25

Creates all base tables:
- users
- projects  
- sites
- layouts
- assets
- roads
- terrain_cache
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry


# revision identifiers, used by Alembic.
revision: str = '001_initial_models'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all initial tables."""
    
    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cognito_sub', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Projects table
    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Sites table
    op.create_table(
        'sites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('boundary', Geometry(geometry_type='POLYGON', srid=4326), nullable=False),
        sa.Column('area_m2', sa.Float(), nullable=True),
        sa.Column('original_file_key', sa.String(512), nullable=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Layouts table
    op.create_table(
        'layouts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('status', sa.String(50), nullable=False, default='queued', index=True),
        sa.Column('error_message', sa.String(1024), nullable=True),
        sa.Column('total_capacity_kw', sa.Float(), nullable=True),
        sa.Column('cut_volume_m3', sa.Float(), nullable=True),
        sa.Column('fill_volume_m3', sa.Float(), nullable=True),
        sa.Column('terrain_processed', sa.Boolean(), nullable=False, default=False),
        sa.Column('site_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Assets table
    op.create_table(
        'assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_type', sa.String(50), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('position', Geometry(geometry_type='POINT', srid=4326), nullable=False),
        sa.Column('capacity_kw', sa.Float(), nullable=True),
        sa.Column('elevation_m', sa.Float(), nullable=True),
        sa.Column('slope_deg', sa.Float(), nullable=True),
        sa.Column('footprint_length_m', sa.Float(), nullable=True),
        sa.Column('footprint_width_m', sa.Float(), nullable=True),
        sa.Column('layout_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('layouts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Roads table
    op.create_table(
        'roads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('geometry', Geometry(geometry_type='LINESTRING', srid=4326), nullable=False),
        sa.Column('length_m', sa.Float(), nullable=True),
        sa.Column('width_m', sa.Float(), nullable=True, default=5.0),
        sa.Column('max_grade_pct', sa.Float(), nullable=True),
        sa.Column('layout_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('layouts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Terrain cache table
    op.create_table(
        'terrain_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('terrain_type', sa.String(50), nullable=False, index=True),
        sa.Column('s3_key', sa.String(512), nullable=False),
        sa.Column('resolution_m', sa.Float(), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('site_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Create spatial indexes (if_not_exists for idempotency - GeoAlchemy2 may auto-create these)
    op.create_index('idx_sites_boundary', 'sites', ['boundary'], postgresql_using='gist', if_not_exists=True)
    op.create_index('idx_assets_position', 'assets', ['position'], postgresql_using='gist', if_not_exists=True)
    op.create_index('idx_roads_geometry', 'roads', ['geometry'], postgresql_using='gist', if_not_exists=True)


def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_index('idx_roads_geometry', table_name='roads')
    op.drop_index('idx_assets_position', table_name='assets')
    op.drop_index('idx_sites_boundary', table_name='sites')
    
    op.drop_table('terrain_cache')
    op.drop_table('roads')
    op.drop_table('assets')
    op.drop_table('layouts')
    op.drop_table('sites')
    op.drop_table('projects')
    op.drop_table('users')

