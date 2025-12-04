"""Add preferred_layout_id to sites table

D-05-06: Allow users to mark a preferred layout variant per site.

Revision ID: 003_preferred_layout
Revises: 002_exclusion_zones
Create Date: 2025-11-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers
revision = '003_preferred_layout'
down_revision = '002_exclusion_zones'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add preferred_layout_id column to sites table."""
    op.add_column(
        'sites',
        sa.Column(
            'preferred_layout_id',
            UUID(as_uuid=True),
            sa.ForeignKey('layouts.id', ondelete='SET NULL'),
            nullable=True,
        )
    )
    
    # Create index for faster lookups
    op.create_index(
        'ix_sites_preferred_layout_id',
        'sites',
        ['preferred_layout_id'],
    )


def downgrade() -> None:
    """Remove preferred_layout_id column from sites table."""
    op.drop_index('ix_sites_preferred_layout_id', table_name='sites')
    op.drop_column('sites', 'preferred_layout_id')






