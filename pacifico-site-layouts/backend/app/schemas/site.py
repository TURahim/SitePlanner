"""
Pydantic schemas for Site API endpoints.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SiteUploadResponse(BaseModel):
    """Response schema for successful site upload."""
    
    id: UUID = Field(..., description="Unique identifier for the created site")
    name: str = Field(..., description="Name of the site (from filename or KML)")
    area_m2: float = Field(..., description="Site area in square meters")
    boundary: dict[str, Any] = Field(..., description="Site boundary as GeoJSON Polygon")
    entry_point: Optional[dict[str, Any]] = Field(None, description="Entry point as GeoJSON Point")
    entry_point_metadata: Optional[dict[str, Any]] = Field(None, description="Metadata for the entry point")
    created_at: datetime = Field(..., description="Timestamp when the site was created")
    
    class Config:
        from_attributes = True


class SiteResponse(BaseModel):
    """Response schema for site retrieval."""
    
    id: UUID
    project_id: Optional[UUID] = None
    name: str
    area_m2: float
    boundary: dict[str, Any] = Field(..., description="Site boundary as GeoJSON")
    entry_point: Optional[dict[str, Any]] = Field(None, description="Entry point as GeoJSON Point")
    entry_point_metadata: Optional[dict[str, Any]] = Field(None, description="Metadata for the entry point")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SiteListItem(BaseModel):
    """Summary schema for site listing."""
    
    id: UUID
    name: str
    area_m2: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class SiteListResponse(BaseModel):
    """Response schema for site listing."""
    
    sites: list[SiteListItem]
    total: int

