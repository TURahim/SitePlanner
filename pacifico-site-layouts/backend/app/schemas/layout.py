"""
Pydantic schemas for Layout API endpoints.

D-05: Added variant generation support with multiple optimization strategies.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.config import get_settings

# Get terrain default from config (environment-specific)
_settings = get_settings()


# =============================================================================
# D-05: Layout Variant Strategies
# =============================================================================


class LayoutStrategy(str, Enum):
    """Layout optimization strategies (D-05)."""
    BALANCED = "balanced"
    DENSITY = "density"
    LOW_EARTHWORK = "low_earthwork"
    CLUSTERED = "clustered"


class StrategyInfo(BaseModel):
    """Information about a layout strategy."""
    strategy: LayoutStrategy
    name: str
    description: str


# Strategy metadata for frontend
STRATEGY_INFO_LIST = [
    StrategyInfo(
        strategy=LayoutStrategy.BALANCED,
        name="Balanced",
        description="Balance capacity, earthwork, and access roads",
    ),
    StrategyInfo(
        strategy=LayoutStrategy.DENSITY,
        name="High Density",
        description="Maximize capacity per hectare",
    ),
    StrategyInfo(
        strategy=LayoutStrategy.LOW_EARTHWORK,
        name="Low Earthwork",
        description="Minimize grading and cut/fill volumes",
    ),
    StrategyInfo(
        strategy=LayoutStrategy.CLUSTERED,
        name="Clustered",
        description="Group assets tightly to minimize infrastructure",
    ),
]


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
    # D-05: Variant generation options
    generate_variants: bool = Field(
        default=False,
        description="D-05: Generate multiple layout variants with different strategies",
    )
    variant_strategies: Optional[list[LayoutStrategy]] = Field(
        default=None,
        description="D-05: Strategies to use (defaults to all 4 if generate_variants=True)",
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
    footprint_length_m: Optional[float] = Field(None, description="Footprint length (N-S) in meters")
    footprint_width_m: Optional[float] = Field(None, description="Footprint width (E-W) in meters")
    # D-02: Per-asset cut/fill volumes (P1)
    cut_m3: Optional[float] = Field(None, description="Cut volume for asset pad grading (m³)")
    fill_m3: Optional[float] = Field(None, description="Fill volume for asset pad grading (m³)")
    # Phase E: Enhanced terrain metrics
    aspect_deg: Optional[float] = Field(None, description="Terrain aspect (slope direction) in degrees, 0-360 clockwise from north")
    suitability_score: Optional[float] = Field(None, description="Composite terrain suitability score (0-1, higher is better)")
    rotation_deg: Optional[float] = Field(None, description="Optimal footprint rotation in degrees")
    
    class Config:
        from_attributes = True


class RoadResponse(BaseModel):
    """Response schema for a road."""
    
    id: UUID
    name: Optional[str] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = Field(5.0, description="Road width in meters")
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
    # Phase E: Enhanced earthwork metrics
    road_cut_m3: Optional[float] = Field(None, description="Cut volume for road corridors (m³)")
    road_fill_m3: Optional[float] = Field(None, description="Fill volume for road corridors (m³)")
    total_cut_m3: Optional[float] = Field(None, description="Total cut volume including roads (m³)")
    total_fill_m3: Optional[float] = Field(None, description="Total fill volume including roads (m³)")
    net_earthwork_m3: Optional[float] = Field(None, description="Net earthwork balance (positive = excess cut)")
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


# =============================================================================
# D-05: Layout Variants Schemas
# =============================================================================


class LayoutVariantMetrics(BaseModel):
    """Metrics for a single layout variant (D-05)."""
    
    layout_id: UUID
    strategy: LayoutStrategy
    strategy_name: str
    total_capacity_kw: float
    asset_count: int
    road_length_m: float
    cut_volume_m3: float
    fill_volume_m3: float
    net_earthwork_m3: float = Field(..., description="cut - fill (positive = export)")
    capacity_per_hectare: Optional[float] = Field(None, description="kW per hectare")


class VariantComparison(BaseModel):
    """
    Comparison analysis across variants (D-05).
    
    Identifies which variant is "best" for each metric category.
    """
    
    best_capacity_id: UUID = Field(..., description="Variant with highest total capacity")
    best_earthwork_id: UUID = Field(..., description="Variant with lowest net earthwork")
    best_road_network_id: UUID = Field(..., description="Variant with shortest total roads")
    metrics_table: list[LayoutVariantMetrics] = Field(
        ..., description="Metrics for each variant in comparison table"
    )


class LayoutVariantResponse(BaseModel):
    """
    Single variant in a multi-variant response (D-05).
    
    Includes the strategy used and full layout data.
    """
    
    strategy: LayoutStrategy
    strategy_name: str
    layout: LayoutResponse
    assets: list[AssetResponse]
    roads: list[RoadResponse]
    geojson: dict[str, Any]


class LayoutVariantsResponse(BaseModel):
    """
    Response for multi-variant layout generation (D-05).
    
    Contains multiple layout variants with comparison analysis.
    """
    
    site_id: UUID
    variants: list[LayoutVariantResponse]
    comparison: VariantComparison
    
    class Config:
        from_attributes = True


class LayoutStrategiesResponse(BaseModel):
    """Response for available layout strategies (D-05)."""
    
    strategies: list[StrategyInfo]

