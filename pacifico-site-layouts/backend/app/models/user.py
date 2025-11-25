"""
User model - represents authenticated users from Cognito.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.site import Site


class User(Base, UUIDMixin, TimestampMixin):
    """
    User model linked to AWS Cognito.
    
    Users are created when they first authenticate via Cognito.
    The cognito_sub is the unique identifier from Cognito.
    """
    
    __tablename__ = "users"
    
    # Cognito subject (unique identifier from Cognito)
    cognito_sub: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    
    # User profile
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    
    # Relationships
    projects: Mapped[list["Project"]] = relationship(
        "Project",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    sites: Mapped[list["Site"]] = relationship(
        "Site",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<User {self.email}>"

