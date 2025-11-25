"""
Pydantic schemas for Layout API endpoints.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.config import get_settings

# Get terrain default from config (environment-specific)
_settings = get_settings()


class GenerateLayoutRequest(BaseModel):
    """Request schema for layout generation."""
    
    site_id: UUID = Field(..., description="ID of the site to generate layout for")
    target_capacity_kw: float = Field(
        default=1000.0,
        ge=100,
        le=100000,
        description="Target total capacity in kW",
    )
    use_terrain: bool = Field(
        default=_settings.use_terrain,  # From config: USE_TERRAIN env var
        description="Use terrain-aware placement (Phase B). Set False for dummy placement.",
    )
    dem_resolution_m: int = Field(
        default=10,
        ge=10,
        le=30,
        description="DEM resolution in meters (10 or 30). Only used if use_terrain=True.",
    )


class AssetResponse(BaseModel):
    """Response schema for an asset."""
    
    id: UUID
    asset_type: str
    name: Optional[str] = None
    capacity_kw: Optional[float] = None
    position: dict[str, Any] = Field(..., description="Position as GeoJSON Point")
    elevation_m: Optional[float] = Field(None, description="Ground elevation in meters")
    slope_deg: Optional[float] = Field(None, description="Terrain slope in degrees")
    
    class Config:
        from_attributes = True


class RoadResponse(BaseModel):
    """Response schema for a road."""
    
    id: UUID
    name: Optional[str] = None
    length_m: Optional[float] = None
    geometry: dict[str, Any] = Field(..., description="Geometry as GeoJSON LineString")
    max_grade_pct: Optional[float] = Field(None, description="Maximum grade along road (%)")
    
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


# =============================================================================
# Phase C: Async Layout Generation Schemas
# =============================================================================


class LayoutEnqueueResponse(BaseModel):
    """Response schema for layout generation job enqueue (C-03)."""
    
    layout_id: UUID = Field(..., description="ID of the queued layout")
    status: str = Field(
        default="queued",
        description="Initial status of the layout job"
    )
    message: str = Field(
        default="Layout generation job queued successfully",
        description="Confirmation message"
    )
    
    class Config:
        from_attributes = True


class LayoutStatusResponse(BaseModel):
    """Response schema for layout status polling (C-04)."""
    
    layout_id: UUID = Field(..., description="ID of the layout")
    status: str = Field(
        ...,
        description="Current status: queued, processing, completed, or failed"
    )
    error_message: Optional[str] = Field(
        None,
        description="Error message if status is 'failed'"
    )
    
    # Populated only when status is 'completed'
    total_capacity_kw: Optional[float] = Field(None, description="Total capacity in kW")
    asset_count: Optional[int] = Field(None, description="Number of assets placed")
    road_length_m: Optional[float] = Field(None, description="Total road length in meters")
    cut_volume_m3: Optional[float] = Field(None, description="Cut volume in cubic meters")
    fill_volume_m3: Optional[float] = Field(None, description="Fill volume in cubic meters")
    
    class Config:
        from_attributes = True

