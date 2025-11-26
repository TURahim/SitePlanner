"""
Layout model - represents a generated layout for a site.

Phase 4 (GAP): Added progress tracking fields (stage, progress_pct, stage_message).
"""
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.road import Road
    from app.models.site import Site


class LayoutStatus(str, Enum):
    """Status of a layout generation job."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class LayoutStage(str, Enum):
    """
    Stages of layout generation for progress tracking (Phase 4 GAP).
    
    Matches LayoutGenerationStage in schemas/layout.py.
    """
    QUEUED = "queued"
    FETCHING_DEM = "fetching_dem"
    COMPUTING_SLOPE = "computing_slope"
    ANALYZING_TERRAIN = "analyzing_terrain"
    PLACING_ASSETS = "placing_assets"
    GENERATING_ROADS = "generating_roads"
    COMPUTING_EARTHWORK = "computing_earthwork"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


class Layout(Base, UUIDMixin, TimestampMixin):
    """
    Layout model representing a generated site layout.
    
    A layout contains assets and roads placed on a site.
    Ownership is derived through the site relationship.
    """
    
    __tablename__ = "layouts"
    
    # Layout status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=LayoutStatus.QUEUED.value,
        index=True,
    )
    
    # Error message if status is FAILED
    error_message: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )
    
    # Phase 4 (GAP): Progress tracking
    stage: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        default=LayoutStage.QUEUED.value,
    )
    
    progress_pct: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=0,
    )
    
    stage_message: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    
    # Layout metrics
    total_capacity_kw: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Cut/fill volumes (from Phase B)
    cut_volume_m3: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    fill_volume_m3: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Whether terrain processing has been completed
    terrain_processed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )
    
    # Site relationship
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # D-05-06: Explicit foreign_keys needed because Site also has preferred_layout_id FK
    site: Mapped["Site"] = relationship(
        "Site",
        back_populates="layouts",
        primaryjoin="Layout.site_id == Site.id",
    )
    
    # Assets in this layout
    assets: Mapped[list["Asset"]] = relationship(
        "Asset",
        back_populates="layout",
        cascade="all, delete-orphan",
    )
    
    # Roads in this layout
    roads: Mapped[list["Road"]] = relationship(
        "Road",
        back_populates="layout",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<Layout {self.id} ({self.status})>"

