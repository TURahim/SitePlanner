"""
Asset model - represents placed infrastructure assets.
"""
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Optional

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.layout import Layout


class AssetType(str, Enum):
    """Types of infrastructure assets."""
    SOLAR_ARRAY = "solar_array"
    BATTERY = "battery"
    GENERATOR = "generator"
    SUBSTATION = "substation"
    TRANSFORMER = "transformer"
    INVERTER = "inverter"


class Asset(Base, UUIDMixin, TimestampMixin):
    """
    Asset model representing an infrastructure component.
    
    Position is stored as a PostGIS POINT geometry.
    """
    
    __tablename__ = "assets"
    
    # Asset type
    asset_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    
    # Asset name/label (optional)
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    
    # Position as PostGIS POINT (SRID 4326 = WGS84)
    position: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=False,
    )
    
    # Capacity in kW
    capacity_kw: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Ground elevation at this position (meters)
    elevation_m: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Terrain slope at this position (degrees)
    slope_deg: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Footprint dimensions (meters)
    footprint_length_m: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    footprint_width_m: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Layout relationship
    layout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("layouts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    layout: Mapped["Layout"] = relationship(
        "Layout",
        back_populates="assets",
    )
    
    def __repr__(self) -> str:
        return f"<Asset {self.asset_type} ({self.capacity_kw}kW)>"

