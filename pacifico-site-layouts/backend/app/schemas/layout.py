"""
Pydantic schemas for Layout API endpoints.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GenerateLayoutRequest(BaseModel):
    """Request schema for layout generation."""
    
    site_id: UUID = Field(..., description="ID of the site to generate layout for")
    target_capacity_kw: float = Field(
        default=1000.0,
        ge=100,
        le=100000,
        description="Target total capacity in kW",
    )


class AssetResponse(BaseModel):
    """Response schema for an asset."""
    
    id: UUID
    asset_type: str
    name: Optional[str] = None
    capacity_kw: Optional[float] = None
    position: dict[str, Any] = Field(..., description="Position as GeoJSON Point")
    
    class Config:
        from_attributes = True


class RoadResponse(BaseModel):
    """Response schema for a road."""
    
    id: UUID
    name: Optional[str] = None
    length_m: Optional[float] = None
    geometry: dict[str, Any] = Field(..., description="Geometry as GeoJSON LineString")
    
    class Config:
        from_attributes = True


class LayoutResponse(BaseModel):
    """Response schema for a layout."""
    
    id: UUID
    site_id: UUID
    status: str
    total_capacity_kw: Optional[float] = None
    cut_volume_m3: Optional[float] = None
    fill_volume_m3: Optional[float] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class LayoutDetailResponse(LayoutResponse):
    """Detailed response including assets and roads."""
    
    assets: list[AssetResponse] = []
    roads: list[RoadResponse] = []


class LayoutGenerateResponse(BaseModel):
    """Response schema for layout generation."""
    
    layout: LayoutResponse
    assets: list[AssetResponse]
    roads: list[RoadResponse]
    geojson: dict[str, Any] = Field(
        ...,
        description="Complete layout as GeoJSON FeatureCollection",
    )


class LayoutListItem(BaseModel):
    """Summary schema for layout listing."""
    
    id: UUID
    site_id: UUID
    status: str
    total_capacity_kw: Optional[float] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class LayoutListResponse(BaseModel):
    """Response schema for layout listing."""
    
    layouts: list[LayoutListItem]
    total: int

