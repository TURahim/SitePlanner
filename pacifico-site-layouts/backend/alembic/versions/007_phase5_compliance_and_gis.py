"""Phase 5 - Compliance Rules & GIS Integration (placeholder)

Revision ID: 007_phase5_compliance
Revises: 006_layout_progress
Create Date: 2025-11-26

Phase 5 introduces:
- Compliance rules engine (runtime-evaluated, no schema changes needed)
- GIS integration service (pluggable provider pattern)
- Wind turbine asset type (added to ASSET_CONFIGS in code)

This migration is a placeholder as compliance rules are evaluated at runtime
and do not require persistent database storage. Rule overrides per layout
can be added to a future "LayoutComplianceOverride" model if needed.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007_phase5_compliance'
down_revision = '006_layout_progress'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Upgrade migration for Phase 5.
    
    No database schema changes needed for Phase 5 initial release.
    Compliance rules are evaluated at runtime using the ComplianceRulesEngine.
    
    Future enhancements could add:
    - LayoutComplianceOverride table for project-specific rule overrides
    - GISIntegrationConfig table for persistent GIS provider settings
    """
    pass


def downgrade() -> None:
    """
    Downgrade migration for Phase 5.
    
    Placeholder - no schema changes to rollback.
    """
    pass
