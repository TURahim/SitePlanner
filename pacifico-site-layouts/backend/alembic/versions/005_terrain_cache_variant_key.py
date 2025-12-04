"""Add variant key to terrain cache and new terrain types

Revision ID: 005_terrain_cache_variant_key
Revises: 004_terrain_layout_extensions
Create Date: 2025-11-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005_terrain_cache_variant_key"
down_revision: Union[str, None] = "004_terrain_layout_extensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "terrain_cache",
        sa.Column("variant_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_terrain_cache_variant_key",
        "terrain_cache",
        ["variant_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_terrain_cache_variant_key", table_name="terrain_cache")
    op.drop_column("terrain_cache", "variant_key")






