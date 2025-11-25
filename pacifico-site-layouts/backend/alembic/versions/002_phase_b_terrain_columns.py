"""Phase B: Add terrain-related columns to assets and roads

Revision ID: 002_phase_b_terrain
Revises: 
Create Date: 2025-11-25

Adds:
- assets.slope_deg: Terrain slope at asset position (degrees)
- roads.max_grade_pct: Maximum grade along road (percent)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_phase_b_terrain'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Phase B terrain columns."""
    # Add slope_deg to assets table (if column doesn't exist)
    op.add_column(
        'assets',
        sa.Column('slope_deg', sa.Float(), nullable=True),
    )
    
    # Add max_grade_pct to roads table (if column doesn't exist)
    op.add_column(
        'roads',
        sa.Column('max_grade_pct', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Remove Phase B terrain columns."""
    op.drop_column('roads', 'max_grade_pct')
    op.drop_column('assets', 'slope_deg')

