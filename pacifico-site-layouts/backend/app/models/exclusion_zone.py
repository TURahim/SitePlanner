"""
Exclusion Zone model - represents areas where assets cannot be placed.

Phase D-03: Exclusion zones allow users to define wetlands, setbacks,
infrastructure buffers, and other constraints that the layout generator
must respect.
"""
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Optional

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.site import Site


class ExclusionZoneType(str, Enum):
    """Types of exclusion zones with associated styling."""
    
    ENVIRONMENTAL = "environmental"  # Wetlands, water bodies, protected areas
    REGULATORY = "regulatory"        # Setbacks, easements, ROW
    INFRASTRUCTURE = "infrastructure"  # Existing utilities, buildings
    SAFETY = "safety"                # Generator noise/emissions buffer
    CUSTOM = "custom"                # User-defined constraints


# Default buffers and colors for each zone type
ZONE_TYPE_DEFAULTS = {
    ExclusionZoneType.ENVIRONMENTAL: {
        "default_buffer_m": 0,
        "color": "#3b82f6",  # Blue
        "description": "Wetlands, water bodies, protected areas",
    },
    ExclusionZoneType.REGULATORY: {
        "default_buffer_m": 0,
        "color": "#ef4444",  # Red
        "description": "Setbacks, easements, ROW",
    },
    ExclusionZoneType.INFRASTRUCTURE: {
        "default_buffer_m": 10,
        "color": "#f97316",  # Orange
        "description": "Existing utilities, buildings",
    },
    ExclusionZoneType.SAFETY: {
        "default_buffer_m": 25,
        "color": "#eab308",  # Yellow
        "description": "Generator noise/emissions buffer",
    },
    ExclusionZoneType.CUSTOM: {
        "default_buffer_m": 0,
        "color": "#6b7280",  # Gray
        "description": "User-defined constraints",
    },
}


class ExclusionZone(Base, UUIDMixin, TimestampMixin):
    """
    Exclusion Zone model representing an area where assets cannot be placed.
    
    The geometry is stored as a PostGIS POLYGON.
    Each exclusion zone belongs to a site.
    """
    
    __tablename__ = "exclusion_zones"
    
    # Zone details
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    # Zone type (enum)
    zone_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ExclusionZoneType.CUSTOM.value,
        index=True,
    )
    
    # Geometry as PostGIS POLYGON (SRID 4326 = WGS84)
    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326),
        nullable=False,
    )
    
    # Additional buffer around the geometry (meters)
    buffer_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    
    # Cost multiplier for pathfinding (1.0 = neutral, >1.0 = avoid, <1.0 = preferred)
    cost_multiplier: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )
    
    # Optional description
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    
    # Calculated area in square meters
    area_m2: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Site relationship (required)
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site: Mapped["Site"] = relationship(
        "Site",
        back_populates="exclusion_zones",
    )
    
    def __repr__(self) -> str:
        return f"<ExclusionZone {self.name} ({self.zone_type})>"
    
    @property
    def effective_buffer_m(self) -> float:
        """Get the effective buffer including type default if not specified."""
        if self.buffer_m > 0:
            return self.buffer_m
        zone_type_enum = ExclusionZoneType(self.zone_type)
        return ZONE_TYPE_DEFAULTS.get(zone_type_enum, {}).get("default_buffer_m", 0)
    
    @property
    def color(self) -> str:
        """Get the display color for this zone type."""
        zone_type_enum = ExclusionZoneType(self.zone_type)
        return ZONE_TYPE_DEFAULTS.get(zone_type_enum, {}).get("color", "#6b7280")

