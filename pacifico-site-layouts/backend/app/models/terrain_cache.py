"""
TerrainCache model - caches DEM and slope data for sites.
"""
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.site import Site


class TerrainType(str, Enum):
    """Types of terrain data that can be cached."""
    ELEVATION = "elevation"        # DEM raster
    SLOPE = "slope"                # Slope raster (degrees)
    ASPECT = "aspect"              # Aspect raster (direction)
    CONTOURS = "contours"          # Generated contour GeoJSON
    SLOPE_HEATMAP = "slope_heatmap"  # Slope zone polygons
    BUILDABLE_AREA = "buildable_area"  # Buildable area polygons


class TerrainCache(Base, UUIDMixin, TimestampMixin):
    """
    TerrainCache model for storing references to cached terrain data.
    
    DEM and slope rasters are stored in S3 and referenced here
    to avoid re-fetching from external APIs.
    """
    
    __tablename__ = "terrain_cache"
    
    # Type of terrain data
    terrain_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    
    # Variant key for parameterized caches (e.g., asset type, interval)
    variant_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    
    # S3 key where the raster is stored
    s3_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    
    # Resolution in meters
    resolution_m: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Data source (e.g., "usgs_3dep", "srtm")
    source: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    
    # Site relationship
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site: Mapped["Site"] = relationship(
        "Site",
        back_populates="terrain_cache",
    )
    
    def __repr__(self) -> str:
        variant = f" ({self.variant_key})" if self.variant_key else ""
        return f"<TerrainCache {self.terrain_type}{variant} for site {self.site_id}>"

