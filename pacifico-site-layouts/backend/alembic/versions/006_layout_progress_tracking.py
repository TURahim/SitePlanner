"""Add progress tracking fields to layouts

Phase 4 (GAP): Adds stage, progress_pct, and stage_message columns
for real-time progress tracking during layout generation.

Revision ID: 006_layout_progress
Revises: 005_terrain_cache_variant_key
Create Date: 2025-11-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006_layout_progress'
down_revision: Union[str, None] = '005_terrain_cache_variant_key'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add progress tracking columns to layouts table."""
    # Add stage column
    op.add_column(
        'layouts',
        sa.Column('stage', sa.String(50), nullable=True, default='queued')
    )
    
    # Add progress_pct column
    op.add_column(
        'layouts',
        sa.Column('progress_pct', sa.Integer(), nullable=True, default=0)
    )
    
    # Add stage_message column
    op.add_column(
        'layouts',
        sa.Column('stage_message', sa.String(255), nullable=True)
    )
    
    # Update existing rows to have default values
    op.execute("""
        UPDATE layouts 
        SET stage = CASE 
            WHEN status = 'completed' THEN 'completed'
            WHEN status = 'failed' THEN 'failed'
            WHEN status = 'processing' THEN 'placing_assets'
            ELSE 'queued'
        END,
        progress_pct = CASE 
            WHEN status = 'completed' THEN 100
            WHEN status = 'failed' THEN 0
            WHEN status = 'processing' THEN 50
            ELSE 0
        END
        WHERE stage IS NULL
    """)


def downgrade() -> None:
    """Remove progress tracking columns."""
    op.drop_column('layouts', 'stage_message')
    op.drop_column('layouts', 'progress_pct')
    op.drop_column('layouts', 'stage')

