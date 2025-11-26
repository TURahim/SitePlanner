"""
Road model - represents access roads connecting assets.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.layout import Layout


class Road(Base, UUIDMixin, TimestampMixin):
    """
    Road model representing access roads.
    
    Geometry is stored as a PostGIS LINESTRING.
    """
    
    __tablename__ = "roads"
    
    # Road name/label (optional)
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    
    # Road geometry as PostGIS LINESTRING (SRID 4326 = WGS84)
    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326),
        nullable=False,
    )
    
    # Length in meters
    length_m: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Road width in meters
    width_m: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        default=5.0,
    )
    
    # Maximum grade along road (percent)
    max_grade_pct: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Road class (spine, secondary, tertiary)
    road_class: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    
    # Parent segment ID for hierarchy
    parent_segment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roads.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # KPI fields
    avg_grade_pct: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    max_cumulative_cost: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    kpi_flags: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
    )
    
    stationing_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
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
        back_populates="roads",
    )
    
    def __repr__(self) -> str:
        return f"<Road {self.name or self.id} ({self.length_m}m)>"

