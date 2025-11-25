"""
Project model - organizes sites into logical groups.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.site import Site
    from app.models.user import User


class Project(Base, UUIDMixin, TimestampMixin):
    """
    Project model for organizing sites.
    
    A project belongs to a user and contains multiple sites.
    """
    
    __tablename__ = "projects"
    
    # Project details
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    
    # Owner relationship
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="projects",
    )
    
    # Sites in this project
    sites: Mapped[list["Site"]] = relationship(
        "Site",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<Project {self.name}>"

