"""
Site model - represents a physical site with a boundary polygon.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.layout import Layout
    from app.models.project import Project
    from app.models.terrain_cache import TerrainCache
    from app.models.user import User


class Site(Base, UUIDMixin, TimestampMixin):
    """
    Site model representing a physical location with a boundary.
    
    The boundary is stored as a PostGIS POLYGON geometry.
    Each site must be owned by a user for multi-tenant isolation.
    """
    
    __tablename__ = "sites"
    
    # Site details
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    # Boundary as PostGIS POLYGON (SRID 4326 = WGS84)
    boundary: Mapped[str] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326),
        nullable=False,
    )
    
    # Calculated area in square meters
    area_m2: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # S3 key for the original uploaded file
    original_file_key: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )
    
    # Project relationship (optional - site can exist without project)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project: Mapped[Optional["Project"]] = relationship(
        "Project",
        back_populates="sites",
    )
    
    # Owner relationship (required for multi-tenant isolation)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="sites",
    )
    
    # Layouts for this site
    layouts: Mapped[list["Layout"]] = relationship(
        "Layout",
        back_populates="site",
        cascade="all, delete-orphan",
    )
    
    # Terrain cache entries
    terrain_cache: Mapped[list["TerrainCache"]] = relationship(
        "TerrainCache",
        back_populates="site",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<Site {self.name}>"

